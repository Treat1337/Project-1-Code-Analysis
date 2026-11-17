# Train trên Google Colab

1. Tải cả thư mục `Colab_Training` lên `MyDrive`.
2. Mở `train_models_colab.ipynb` bằng Google Colab.
3. Chọn `Runtime > Change runtime type > T4 GPU`.
4. Chạy các cell theo thứ tự.

Notebook sẽ mount Drive, cài `requirements-ml.txt`, kiểm tra CUDA, đọc trực tiếp
từng file trong `Dataset/Project_CodeNet` và chạy TF-IDF, CodeBERT và ASTNN.
`problem_descriptions` được nạp để hiển thị đề, `derived/input_output` để lấy
test mẫu, `metadata` để lấy verdict, còn `data` chứa source code. Không cần
`codenet_verdicts.csv`. Bộ đọc lấy tối đa 500 source C++ cân bằng cho mỗi nhãn
để tránh nạp toàn bộ hàng triệu submission vào RAM. Checkpoint và
`comparison.json` được lưu trong `artifacts/code-models/`.

Các file Python trong `scripts/` và `app/services/` là module model được
notebook gọi; không cần chuyển từng module thành notebook cell.
