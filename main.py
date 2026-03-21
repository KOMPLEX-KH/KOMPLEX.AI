from app.grpc.ai_grpc_service import serve
import uvicorn
import threading

if __name__ == "__main__":
    grpc_thread = threading.Thread(target=serve, daemon=True)
    grpc_thread.start()

    uvicorn.run("app.app:app", host="127.0.0.1", port=8000, reload=False)