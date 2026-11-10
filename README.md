# Trợ giảng phân tích code C++

MVP cho đề tài AI hỗ trợ sinh viên học lập trình: FastAPI cung cấp API, Streamlit là giao diện, Docker chạy C++17 trong container bị giới hạn, TF-IDF truy xuất tài liệu tiếng Việt, LLM tương thích OpenAI tùy chọn và baseline ML được bật khi có CSV có nhãn.

## Yêu cầu

- Python 3.12 trở lên
- Docker Desktop đang chạy
- Git Bash hoặc PowerShell trên Windows

Các tệp mã nguồn thô trong `Dataset/Project_CodeNet/data` không được đưa vào
repository vì bộ dữ liệu này rất lớn. Metadata CodeNet cũng được loại khỏi
repository vì chứa hàng triệu bản ghi; hãy cung cấp thư mục metadata khi chạy
các script chuẩn bị dữ liệu. Mô tả bài toán và dữ liệu dẫn xuất cần thiết cho
ứng dụng vẫn được giữ lại. Các model và benchmark sinh ra trong quá trình
huấn luyện cũng bị loại khỏi repository; chúng có thể được tạo lại bằng các
script trong `scripts`.

**Không cài Docker thì hệ thống vẫn mở được API và giao diện nhưng sẽ từ chối chạy code.** Không thay sandbox bằng chạy `g++` trực tiếp trên máy chủ. Không dùng hệ thống này làm sandbox production đa người dùng; Docker chia sẻ kernel với host.

Giao diện Streamlit dùng editor C++ có tô sáng cú pháp, tải đề bài từ `Dataset/Project_CodeNet/problem_descriptions` và ưu tiên input/output mẫu từ `Dataset/Project_CodeNet/derived/input_output/data` (fallback về ví dụ trong HTML), rồi chia kết quả Docker, phản hồi học tập cùng tài liệu liên quan thành các tab. Runner hiện không đo bộ nhớ hoặc thời gian riêng cho từng test; giao diện nêu rõ giới hạn này.

## Cài đặt trên Windows

Mở PowerShell tại thư mục `Code_Analysis`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker build -t code-analysis-runner:latest -f runner\Dockerfile runner
```

Khởi động API trong cửa sổ đầu tiên:

```powershell
uvicorn app.main:app --reload
```

Khởi động giao diện trong cửa sổ thứ hai:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run ui.py
```

Hoặc chạy toàn bộ quy trình cài đặt và khởi động API/giao diện trong cùng một cửa sổ PowerShell:

```powershell
py -3.12 run.py
```

Script tự tạo `.venv` nếu chưa có, cài dependencies, thử build Docker runner rồi mở API và giao diện. Nhấn `Ctrl+C` để dừng cả hai. Nếu Docker chưa cài hoặc chưa chạy, API/giao diện vẫn mở nhưng chức năng biên dịch và chạy code sẽ không khả dụng.

Mở `http://localhost:8501`; tài liệu API ở `http://127.0.0.1:8000/docs`.

## LLM (tùy chọn)

Mặc định, phản hồi được tạo cục bộ từ verdict và tài liệu đã truy xuất; không cần API key. Nếu chủ động muốn dùng LLM tương thích OpenAI, đặt các biến môi trường trước khi chạy API:

```powershell
$env:AI_API_KEY = "your-key"
$env:AI_BASE_URL = "https://api.openai.com/v1"
$env:AI_MODEL = "gpt-4o-mini"
uvicorn app.main:app --reload
```

Khi bật LLM, code, chẩn đoán, cảnh báo compiler và `learning_context` (nếu có) được gửi tới nhà cung cấp đã cấu hình. Xem xét quyền riêng tư và chính sách của nhà cung cấp trước khi dùng.

## API

- `GET /health`: tình trạng Docker runner, LLM và classifier
- `POST /analyze`: biên dịch, chạy các test và nhận giải thích; có thể truyền `problem_id` để tìm code tham chiếu chỉ trong cùng bài toán (`similarity_limit` mặc định 5, tối đa 10)
- `POST /feedback`: truy xuất tài liệu và sinh phản hồi cho verdict có sẵn
- `POST /classify`: thử nghiệm dự đoán ML; không ghi đè kết quả runner
- `POST /learning/trace`: dự đoán tiến trình từ lịch sử test case được gửi trong request
- `POST /misconceptions/analyze`: gom nhóm code/chẩn đoán tương tự để giảng viên xem xét
- `GET /knowledge/search?q=...`: truy xuất các đoạn kiến thức

Ví dụ request:

```json
{
  "code": "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<'\\n';}",
  "test_cases": [
    {"stdin": "2 3\n", "expected_stdout": "5\n"}
  ]
}
```

Các verdict thực thi: `COMPILE_ERROR`, `WRONG_ANSWER`, `RUNTIME_ERROR`, `TIME_LIMIT_EXCEEDED`, `ACCEPTED`. Verdict `ACCEPTED` chỉ áp dụng với test được gửi.

Khi có `problem_id`, `/analyze` đọc metadata CodeNet của đúng bài, lập chỉ mục TF-IDF theo ký tự cho tối đa 100 submission mỗi verdict và trả `code_retrieval` gồm top-K code tương tự cùng submission gần nhất theo từng verdict tìm thấy. Chỉ mục từng bài được cache trong tiến trình API; khởi động lại API để nạp thay đổi dataset. File code lớn hơn 64 KiB bị bỏ qua. Điểm tương đồng là tín hiệu từ cấu trúc ký tự, không chứng minh tính đúng đắn.

Feedback của `/analyze` không còn chỉ dựa trên câu `Output did not match...`. Runner trả kèm input, output thực tế, output mong đợi và `output_diff.first_difference` cho mỗi test `WRONG_ANSWER`; feedback local và LLM dùng các dữ liệu này để nêu khác biệt đầu tiên. Đây là bằng chứng về test làm lộ lỗi, không phải bằng chứng chắc chắn về dòng source gây lỗi. Nếu chưa có compiler location hoặc công cụ fault localization, hệ thống phải nói rõ chưa thể kết luận dòng sai thay vì tự đoán. `error_localization` vẫn trích dòng/cột compiler báo và các test thất bại. Metadata CodeNet hiện dùng ở đây không chứa kết quả từng test, nên hệ thống không tuyên bố đối chiếu được test phân biệt giữa submission Accepted và sai.

### Truy vết tiến trình và phát hiện mẫu lỗi

Mỗi mô hình nằm trong một module riêng ở `app/services`: baseline TF-IDF trong `classifier.py`, CodeBERT trong `codebert_model.py`, ASTNN trong `astnn_model.py`, mô hình truy vết trong `knowledge_tracing.py`, gom nhóm lỗi trong `misconception_detection.py`, và RAG/LLM trong `feedback.py`.

`POST /learning/trace` nhận lịch sử theo thứ tự từ cũ đến mới. Mỗi test cần có `case_id` ổn định (hoặc trường `case` trong output từ runner) và trạng thái `PASSED`, `WRONG_ANSWER`, `RUNTIME_ERROR` hoặc `TIME_LIMIT_EXCEEDED`:

```json
{
  "history": [
    {"verdict": "WRONG_ANSWER", "tests": [{"case_id": 1, "status": "WRONG_ANSWER"}]},
    {"verdict": "ACCEPTED", "tests": [{"case_id": 1, "status": "PASSED"}]}
  ],
  "next_test_case_ids": [1]
}
```

Kết quả bao gồm xác suất ước tính cho từng test, trạng thái mastery ẩn, xác suất đạt toàn bộ test được yêu cầu, xu hướng và lỗi/test lặp lại. Đây là baseline trạng thái ẩn rời rạc kiểu BKT với tham số cố định, lấy cảm hứng từ truy vết test-case; không phải mô hình RSSM/TIKTOC đã huấn luyện. Ước tính đạt toàn bộ test giả định các test độc lập. API không lưu lịch sử giữa các request, nên ứng dụng gọi API cần gửi lại lịch sử.

`POST /misconceptions/analyze` nhận ít nhất hai lần nộp có code, verdict và chẩn đoán. TF-IDF + DBSCAN gom những lần nộp có nội dung tương đồng; các cụm chỉ là mẫu để giảng viên xem xét, không chứng minh được suy nghĩ hay quan niệm của sinh viên, và không phải bản tái hiện đã kiểm chứng của MISTAKE.

Có thể truyền kết quả các mô hình lịch sử vào `learning_context` của `POST /feedback` để RAG/LLM cân nhắc cùng verdict, cảnh báo compiler, chẩn đoán và tài liệu truy xuất. Runner bật `-Wall -Wextra -Wpedantic` để cung cấp cảnh báo compile-time cơ bản; đây không phải công cụ phân tích tĩnh chuyên dụng. Mặc định phản hồi vẫn được tạo cục bộ. Không gửi code/lịch sử có thông tin cá nhân nếu chưa có sự đồng ý và chính sách lưu trữ phù hợp.

## Baseline ML

Classifier dùng TF-IDF ký tự + Logistic Regression. Khi có dữ liệu được phép sử dụng, tạo `Dataset/labeled_examples.csv` có header `code,label` (có thể thêm `compiler_message`), tối thiểu hai nhãn và hai ví dụ mỗi nhãn, rồi khởi động lại API. Dự đoán chỉ là thử nghiệm; cần đánh giá bằng train/test split, Macro-F1 và confusion matrix trước khi đưa ra kết luận nghiên cứu. Không dùng nhãn suy diễn thiếu căn cứ; nhãn verdict đáng tin cậy cần dựa trên compiler/test runner.

### Train từng model

Project CodeNet cung cấp nhãn trạng thái submission nhưng không có `compiler_message`. Chuẩn bị CSV cân bằng tối đa 500 mẫu mỗi nhãn:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_codenet_dataset.py --max-per-label 500
```

Các model CodeBERT và ASTNN cần dependency tùy chọn trong `requirements-ml.txt`. Cài chúng vào virtualenv trước khi train; dùng cùng interpreter để chạy script (tránh gọi `python` nếu nó trỏ ra ngoài `.venv`):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
```

Train riêng từng model:

```powershell
.\.venv\Scripts\python.exe scripts\train_classifier.py --dataset Dataset\codenet_verdicts.csv
.\.venv\Scripts\python.exe scripts\train_codebert.py --dataset Dataset\codenet_verdicts.csv --epochs 3 --batch-size 8 --max-length 256
.\.venv\Scripts\python.exe scripts\train_astnn.py --dataset Dataset\codenet_verdicts.csv --epochs 3 --batch-size 8
```

Hoặc train tuần tự cả ba model và dừng tại model lỗi đầu tiên:

```powershell
.\.venv\Scripts\python.exe scripts\train_all_models.py --dataset Dataset\codenet_verdicts.csv --epochs 3 --batch-size 8 --max-length 256
```

Mỗi script in số mẫu đã đọc, số mẫu train/test, model hiện tại, epoch và tiến độ mẫu đã xử lý. CSV được chia train/test theo `problem_id` khi có cột này để tránh cùng bài toán xuất hiện ở cả hai tập. Checkpoint và `metrics.json` được lưu trong `artifacts\code-models\<model>`; report CodeBERT/ASTNN cũng được tổng hợp trong `comparison.json`. Lần đầu chạy CodeBERT cần mạng để tải checkpoint `microsoft/codebert-base`. Hãy bắt đầu với `--max-per-label 50` và `--epochs 1` để kiểm tra quy trình trước khi train lâu hơn.

Classifier TF-IDF + Logistic Regression lưu thành `artifacts\code-models\classifier\model.joblib` và được API tự nạp khi khởi động lại. Để dùng CodeBERT hoặc ASTNN, trỏ biến môi trường tới checkpoint tương ứng:

```powershell
$env:NEURAL_MODEL_DIR = "artifacts\code-models\astnn"
uvicorn app.main:app --reload
```

Đổi `astnn` thành `codebert` để chọn model kia. Nếu máy có GPU NVIDIA nhưng PyTorch báo `CUDA available: False`, môi trường hiện dùng bản PyTorch CPU; có thể train trên CPU bằng cách bỏ `--device cuda`, nhưng CodeBERT sẽ chậm. Cài PyTorch CUDA phù hợp với driver trước khi truyền `--device cuda`.

RSSM/TIKTOC trong dự án hiện là baseline truy vết trạng thái với tham số cố định, chưa có pipeline huấn luyện; `/misconceptions/analyze` là gom cụm TF-IDF/DBSCAN theo lịch sử gửi lên chứ chưa học checkpoint; RAG/LLM không fine-tune model mà dùng knowledge base và LLM provider. Vì vậy `train_all_models.py` chỉ chạy các model trainable: classifier, CodeBERT, ASTNN. Tất cả dự đoán ML vẫn mang tính thử nghiệm và không thay thế verdict compiler/test runner.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Các kiểm thử cục bộ không thực thi code C++ gửi lên. Tích hợp runner cần Docker đang chạy và image được build thành công.

Đánh giá baseline ML trên tập CSV bằng:

```powershell
python scripts\evaluate_classifier.py
```
#   P r o j e c t - 1 - C o d e - A n a l y s i s  
 