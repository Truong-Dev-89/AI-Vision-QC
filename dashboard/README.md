# dashboard/

Giao diện web (index.html) kết nối trực tiếp webcam/camera, gọi thẳng API
trong api/app.py. Được phục vụ tự động cùng lúc với API — chỉ cần chạy:

    uvicorn api.app:app --reload --port 8000

rồi mở trình duyệt vào http://127.0.0.1:8000/ui/

Không mở file index.html trực tiếp (double-click) vì sẽ thiếu quyền gọi
API đúng cách trên một số trình duyệt — luôn mở qua địa chỉ /ui/ ở trên.
