import logging
from pathlib import Path
from enum import Enum
from adapter import kordoc
from config import BASE_DIR

# 1. 경로 상수화
RAW_DIR = BASE_DIR / "data" / "01_raw"
CONVERTED_DIR = BASE_DIR / "data" / "02_converted"

class RawContractFile(Enum):
    """data/01_raw 디렉토리 내의 원본 HWP 계약서 파일 경로에 대한 타입 세이프 Enum 상수를 제공합니다."""
    SW_EMPLOYMENT = RAW_DIR / "201231_SW종사자_기간제,단시간__표준근로계약서.hwp"
    SW_FREELANCE = RAW_DIR / "201231_SW종사자_표준도급계약서.hwp"
    SW_SUPPLY = RAW_DIR / "붙임1_상용SW_공급구축_사업_표준계약서.hwp"
    SW_MAINTENANCE = RAW_DIR / "붙임2_상용SW_유지관리_사업_표준계약서.hwp"
    SYS_DEV = RAW_DIR / "붙임3_정보시스템_개발구축_사업_표준계약서.hwp"
    SYS_MAINTENANCE = RAW_DIR / "붙임4_정보시스템_유지관리_사업_표준계약서.hwp"

def convert_raw_to_markdown(raw_file: RawContractFile) -> Path:
    """
    kordoc MCP 어댑터를 사용하여 원본 HWP 계약서 파일을 
    data/02_converted 디렉토리 내에 동명의 마크다운(.md) 파일로 변환하여 저장합니다.
    
    Args:
        raw_file (RawContractFile): 변환 대상이 되는 원본 계약서 Enum 멤버
        
    Returns:
        Path: 생성 완료된 마크다운 파일의 절대 경로
    """
    input_path = raw_file.value
    
    if not input_path.exists():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {input_path}")
        
    # 출력 디렉토리 자동 생성
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    
    output_filename = f"{input_path.stem}.md"
    output_path = CONVERTED_DIR / output_filename
    
    logging.debug(f"🔄 HWP 변환 시작: {input_path.name} -> {output_filename}")
    
    # kordoc MCP 어댑터를 사용해 마크다운 변환 수행
    success = kordoc.parse_to_markdown(str(input_path), str(output_path))
    
    if success and output_path.exists():
        logging.debug(f"✨ 변환 완료: {output_path}")
        return output_path
    else:
        raise RuntimeError(f"kordoc 변환 작업이 실패했습니다 (파일 미생성): {input_path.name}")

if __name__ == "__main__":
    # 스크립트 직접 실행 시 예시로 표준도급계약서 변환 테스트 수행
    try:
        converted_file = convert_raw_to_markdown(RawContractFile.SW_FREELANCE)
    except Exception as e:
        logging.error(f"❌ 변환 오류: {e}")
