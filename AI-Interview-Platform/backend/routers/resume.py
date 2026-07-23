"""简历解析路由"""
from fastapi import APIRouter, UploadFile, File, HTTPException

from services.resume_parser import extract_text_from_file, extract_resume

router = APIRouter()


@router.post("/parse")
async def parse_resume(file: UploadFile = File(...)):
    """上传简历文件并解析为结构化数据"""
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 Word(.docx) 格式")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    try:
        raw_text = extract_text_from_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="文件解析失败，请检查文件格式")

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="未能从文件中提取到文本内容")

    resume_data = extract_resume(raw_text)
    return {"status": "ok", "data": resume_data, "raw_text_length": len(raw_text)}
