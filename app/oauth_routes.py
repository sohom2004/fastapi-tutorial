from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.oauth import oauth
from app.db import User, get_async_session
from app.users import get_jwt_strategy

router = APIRouter(
    prefix="/auth/google",
    tags=["Google OAuth"]
)

@router.get("/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/callback", name="google_callback")
async def google_callback(request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google.")
        email = user_info.get("email")
        google_id = user_info.get("sub")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in Google user info.")
        
        result = await session.execute(
            select(User).where(User.email == email)
        )
        
        user = result.scalars().first()
        
        if user is None:
            user = User(
                email = email,
                hashed_password = "",
                is_active = True,
                is_verified = True,
                is_superuser = False,
                google_id = google_id
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            if not getattr(user, "google_id", None):
                user.google_id = google_id
                await session.commit()
            
        strategy = get_jwt_strategy()
        access_token = await strategy.write_token(user)
        return RedirectResponse(
            url=f"http://localhost:8501/?token={access_token}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
