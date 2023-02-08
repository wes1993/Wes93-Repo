import mimetypes
import os

import magic
import secrets

import json  
f = open('/data/options.json')

data = json.loads(f)  
name = data["name"]  
password = data["password"]  
print(name)  
# Output: John  
print(password)  
# Output: 30 


from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.background import BackgroundTasks
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from util.sub import download_subs
from util.meta import query_meta
from util.stream import stream_from_yt

app = FastAPI()

security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = b"pluto"
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = b"pippo"
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/")
def read_current_user(username: str = Depends(get_current_username)):
    return {"usefghfghfhrname": username}


@app.get("/dl/{video_id}")
async def api_dl(
    video_id: str,   # the video's ID (watch?v=<this>)
    f: str = "best", # format 
    sl: str = None,  # subtitle language to embed
    username: str = Depends(get_current_username)
):
    stream = stream_from_yt(video_id, f, sl)  
    first_chunk = await stream.__anext__() # peek first chunk

    # guess filetype
    m = magic.Magic(mime=True, uncompress=True)
    mime_type = m.from_buffer(first_chunk)

    # guess extension based on mimetype
    ext = mimetypes.guess_extension(mime_type) or '.mkv' # fallback to mkv I guess
    
    print(f"[{video_id}]: download type: {mime_type} ({ext})")
    
    headers = {
        "Content-Disposition": f"attachment;filename={video_id}{ext}"
    }

    async def joined_stream():
        # attach the first chunk back to the generator
        yield first_chunk

        # pass on the rest
        async for chunk in stream:
            yield chunk

    # pass that to the user
    return StreamingResponse(
        joined_stream(),
        media_type = mime_type,
        headers = headers
    )

@app.get("/meta/{video_id}")
async def api_meta(video_id: str, username: str = Depends(get_current_username)):
    username: str = Depends(get_current_username)
    meta = query_meta(video_id)
    if meta is None:
        raise HTTPException(
            status_code=400, 
            detail="Could not get meta for requested Video ID!"
        )

    return JSONResponse(meta)


def _remove_file(path: str) -> None:
    if not (
        path.endswith('.vtt')
        or path.endswith('.srt')
        or path.endswith('.ass')
    ):
        # don't delete weird files
        # better safe than sorry
        return
    os.remove(path)

@app.get("/sub/{video_id}")
async def api_sub(background_tasks: BackgroundTasks, video_id: str, l: str = "en", f: str = "vtt", username: str = Depends(get_current_username)):
    if f not in ["vtt", "ass", "srt"] and not (l == "live_chat" and f == "json"):
        raise HTTPException(
            status_code=400,
            detail="Invalid subtitle format, valid options are: vtt, ass, srt"
        )
    
    sub_file = download_subs(video_id, l, f)
    
    background_tasks.add_task(_remove_file, sub_file)
    
    return FileResponse(
        sub_file,
        filename=f"{video_id}.{l}.{f}"
    )
