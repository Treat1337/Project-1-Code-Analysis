from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import torch
import tree_sitter_cpp
from torch import Tensor, nn
from tree_sitter import Language, Parser


ASTNN_HIDDEN_SIZE = 128
ASTNN_EMBEDDING_SIZE = 128
ASTNN_MAX_NODES = 4096
ASTNN_MAX_STATEMENTS = 256
ASTNN_UNKNOWN_TOKEN = "<UNK>"

AstTree = tuple[int, tuple["AstTree", ...]]


def create_cpp_parser() -> Parser:
    return Parser(Language(tree_sitter_cpp.language()))


def _terminal_label(node: Any, source: bytes) -> str:
    if not node.is_named:
        return node.type
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    if node.type in {"identifier", "field_identifier", "type_identifier"}:
        return "IDENTIFIER"
    if re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[uUlLfF]*", text):
        return "NUMBER"
    if text.startswith(("'", '"')):
        return "STRING"
    return node.type


def _statement_nodes(root: Any) -> list[Any]:
    statements: list[Any] = []
    for top_level in root.named_children:
        if top_level.type == "function_definition":
            body = next(
                (child for child in top_level.named_children if child.type == "compound_statement"),
                None,
            )
            if body is not None:
                statements.extend(body.named_children)
                continue
        statements.append(top_level)
    if not statements:
        statements.append(root)
    return statements[:ASTNN_MAX_STATEMENTS]


def _node_tokens(node: Any, source: bytes, tokens: set[str], budget: list[int]) -> None:
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if node.child_count == 0:
        tokens.add(_terminal_label(node, source))
        return
    tokens.add(node.type)
    for child in node.children:
        _node_tokens(child, source, tokens, budget)


def build_ast_vocabulary(codes: list[str], parser: Parser) -> dict[str, int]:
    tokens = {ASTNN_UNKNOWN_TOKEN}
    for code in codes:
        source = code.encode("utf-8", errors="replace")
        root = parser.parse(source).root_node
        budget = [ASTNN_MAX_NODES]
        for node in _statement_nodes(root):
            _node_tokens(node, source, tokens, budget)
            if budget[0] <= 0:
                break
    return {token: index for index, token in enumerate(sorted(tokens))}


def encode_ast(code: str, vocabulary: dict[str, int], parser: Parser) -> list[AstTree]:
    source = code.encode("utf-8", errors="replace")
    root = parser.parse(source).root_node
    unknown_id = vocabulary[ASTNN_UNKNOWN_TOKEN]
    budget = [ASTNN_MAX_NODES]

    def encode_node(node: Any) -> AstTree:
        if budget[0] <= 0:
            return unknown_id, ()
        budget[0] -= 1
        label = _terminal_label(node, source) if node.child_count == 0 else node.type
        children = tuple(encode_node(child) for child in node.children)
        return vocabulary.get(label, unknown_id), children

    trees: list[AstTree] = []
    for node in _statement_nodes(root):
        if budget[0] <= 0:
            break
        trees.append(encode_node(node))
    if not trees:
        trees.append((unknown_id, ()))
    return trees


class ChildSumTreeLSTM(nn.Module):
    def __init__(self, vocabulary_size: int, embedding_size: int, hidden_size: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embedding_size)
        self.input_gates = nn.Linear(embedding_size, 3 * hidden_size)
        self.hidden_gates = nn.Linear(hidden_size, 3 * hidden_size, bias=False)
        self.input_forget = nn.Linear(embedding_size, hidden_size)
        self.hidden_forget = nn.Linear(hidden_size, hidden_size, bias=False)
        self.hidden_size = hidden_size

    def encode_tree(self, tree: AstTree) -> Tensor:
        token_id, children = tree
        child_states = [self.encode_tree(child) for child in children]
        child_h = [state[0] for state in child_states]
        child_c = [state[1] for state in child_states]
        embedding = self.embedding(torch.tensor(token_id, device=self.embedding.weight.device))
        summed_h = torch.stack(child_h).sum(dim=0) if child_h else embedding.new_zeros(self.hidden_size)
        input_gate, output_gate, update = (
            self.input_gates(embedding) + self.hidden_gates(summed_h)
        ).chunk(3, dim=-1)
        cell = torch.sigmoid(input_gate) * torch.tanh(update)
        if child_states:
            forget_gates = torch.stack(
                [
                    torch.sigmoid(self.input_forget(embedding) + self.hidden_forget(state[0]))
                    for state in child_states
                ]
            )
            cell = cell + (forget_gates * torch.stack(child_c)).sum(dim=0)
        hidden = torch.sigmoid(output_gate) * torch.tanh(cell)
        return hidden, cell


class ASTNNClassifier(nn.Module):
    def __init__(self, vocabulary_size: int, class_count: int) -> None:
        super().__init__()
        self.tree_encoder = ChildSumTreeLSTM(
            vocabulary_size, ASTNN_EMBEDDING_SIZE, ASTNN_HIDDEN_SIZE
        )
        self.statement_encoder = nn.GRU(
            ASTNN_HIDDEN_SIZE,
            ASTNN_HIDDEN_SIZE // 2,
            batch_first=True,
            bidirectional=True,
        )
        self.attention = nn.Linear(ASTNN_HIDDEN_SIZE, 1)
        self.classifier = nn.Linear(ASTNN_HIDDEN_SIZE, class_count)

    def forward(self, batch: list[list[AstTree]]) -> Tensor:
        logits: list[Tensor] = []
        for sample in batch:
            statement_vectors = torch.stack(
                [self.tree_encoder.encode_tree(tree)[0] for tree in sample]
            ).unsqueeze(0)
            encoded, _ = self.statement_encoder(statement_vectors)
            weights = torch.softmax(self.attention(encoded).squeeze(-1), dim=-1)
            pooled = torch.sum(encoded * weights.unsqueeze(-1), dim=1)
            logits.append(self.classifier(pooled.squeeze(0)))
        return torch.stack(logits)


class TrainedASTNNModel:
    def __init__(
        self, model_dir: Path, metadata: dict[str, Any], device: torch.device
    ) -> None:
        self.device = device
        self.labels: list[str] = metadata["labels"]
        self.vocabulary: dict[str, int] = metadata["vocabulary"]
        self.parser = create_cpp_parser()
        self.model = ASTNNClassifier(len(self.vocabulary), len(self.labels))
        state = torch.load(model_dir / "model.pt", map_location=device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.to(device)
        self.model.eval()

    def predict(self, code: str, _compiler_message: str = "") -> dict[str, Any]:
        with torch.no_grad():
            trees = encode_ast(code, self.vocabulary, self.parser)
            logits = self.model([trees])[0]
            probabilities = torch.softmax(logits, dim=-1)
            confidence, index = torch.max(probabilities, dim=-1)
        return {
            "available": True,
            "label": self.labels[int(index)],
            "confidence": round(float(confidence), 4),
            "note": "Experimental prediction only; never overrides the compiler or test runner verdict.",
        }
