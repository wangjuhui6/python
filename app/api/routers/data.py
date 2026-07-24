from fastapi import APIRouter

router = APIRouter(prefix="/data", tags=["DATA"])

@router.get("")
def read_root():
    return {"message": "Hello, World!"}
