"""Development launcher: `python run.py`"""

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    print(f"  {settings.APP_NAME} — Guest Management System")
    print(f"  App     http://{settings.HOST}:{settings.PORT}")
    print(f"  Docs    http://{settings.HOST}:{settings.PORT}/api/docs")
    print()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.APP_ENV == "development",
        log_level="info",
    )
