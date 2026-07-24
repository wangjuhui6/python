from fastapi import APIRouter

router = APIRouter(prefix="/base", tags=["BASE"])

@router.get("")
def read_root():
    return {"message": "base!"}

@router.get("/detail")
def read_root():
    return {"message": "base! detail"}
