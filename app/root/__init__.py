from fastapi import APIRouter

router = APIRouter(tags=["root"])


@router.get("/")
async def root():
    return {"message": "Hello from baby-backend"}
