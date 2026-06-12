from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from app.db import create_db_and_tables, get_async_session, Post, User
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imagekit
import shutil
import os
import uuid
from app.users import current_active_user, auth_backend, fastapi_users
from app.schemas import UserRead, UserCreate, UserUpdate

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"])

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)):
    
        try:
            response = imagekit.files.upload(
                file=file.file,
                file_name=file.filename,
                use_unique_file_name=True,
                folder="/uploads/",
                tags=["backend-upload"]
            )
            post = Post(
                user_id=user.id,
                caption=caption,
                url=response.url,
                file_type="video" if file.content_type.startswith("video/") else "image",
                file_name=response.name
            )
            
            session.add(post)
            await session.commit()
            await session.refresh(post)
            return post
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            file.file.close()
    
@app.get("/feed")
async def get_feed(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts = [row[0] for row in result.all()]
    result = await session.execute(select(User))
    users = [row[0] for row in result.all()]
    user_dict = {u.id: u.email for u in users}
    post_data = []
    for post in posts:
        post_data.append({
            "id": post.id,
            "user_id": post.user_id,
            "caption": post.caption,
            "url": post.url,
            "file_type": post.file_type,
            "file_name": post.file_name,
            "created_at": post.created_at,
            "is_owner": post.user_id == user.id,
            "email": user_dict.get(post.user_id, "Unknown")
        })
    return {"post": post_data}

@app.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    post_uuid = uuid.UUID(post_id)
    
    result = await session.execute(select(Post).where(Post.id == post_uuid))
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")
    
    try:
        await session.delete(post)
        await session.commit()
        return {"detail": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))