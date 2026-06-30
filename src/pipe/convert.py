import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    SI_SUBCONTRACT = RAW_DIR / "221228_상용소프트웨어_공급개발구축업.hwp"
    SI_SUBCONTRACT_FULL = RAW_DIR / "251221_상용소프트웨어공급개발구축업종(비밀유지계약서_통합_및_안전등_추가).hwp"
    SM_SUBCONTRACT = RAW_DIR / "221228_상용소프트웨어_유지관리업종.hwp"
    SM_SUBCONTRACT_FULL = RAW_DIR / "251221_상용소프트웨어유지관리업종(비밀유지계약서_통합_및_안전_추가).hwp"

def convert_raw_to_markdown(input_path: Path) -> Path:
    """
    kordoc MCP 어댑터를 사용하여 원본 HWP 계약서 파일을 
    data/02_converted 디렉토리 내에 동명의 마크다운(.md) 파일로 변환하여 저장합니다.
    
    Args:
        raw_file (RawContractFile): 변환 대상이 되는 원본 계약서 Enum 멤버
        
    Returns:
        Path: 생성 완료된 마크다운 파일의 절대 경로
    """
    
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
        # [후처리] 하도급 통합 마크다운 파일인 경우 물리적 5종 분할 및 조항 보정 진행
        if "상용소프트웨어" in input_path.name:
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    full_content = f.read()

                # 분할 랜드마크 검색 (시작 오프셋 찾기)
                import re
                nda_pattern = r"(?:\n|^)(#+\s*(?:비밀정보\s*및\s*기술자료의\s*)?비밀유지계약서)"
                direct_pattern = r"(?:\n|^)(#+\s*하도급대금\s*직접지급\s*합의서)"
                modify_pattern = r"(?:\n|^)(#+\s*표준약식변경\s*(?:하도급)?계약서)"
                index_pattern = r"(?:\n|^)(#+\s*표준\s*연동계약서)"

                nda_match = re.search(nda_pattern, full_content)
                direct_match = re.search(direct_pattern, full_content)
                modify_match = re.search(modify_pattern, full_content)
                index_match = re.search(index_pattern, full_content)

                nda_idx = nda_match.start() if nda_match else len(full_content)
                direct_idx = direct_match.start() if direct_match else len(full_content)
                modify_idx = modify_match.start() if modify_match else len(full_content)
                index_idx = index_match.start() if index_match else len(full_content)

                # 각 슬라이스 오프셋 정렬
                offsets = [
                    (0, "main", nda_idx),
                    (nda_idx, "비밀유지계약서", direct_idx),
                    (direct_idx, "직접지급합의서", modify_idx),
                    (modify_idx, "약식변경계약서", index_idx),
                ]
                if index_match:
                    offsets.append((index_idx, "연동계약서", len(full_content)))
                else:
                    offsets[-1] = (modify_idx, "약식변경계약서", len(full_content))

                for start, suffix, end in offsets:
                    if start >= len(full_content) or start >= end:
                        continue
                        
                    slice_content = full_content[start:end].strip()
                    if not slice_content:
                        continue

                    # 고정밀 조항 헤더 ### 달아주기
                    slice_content = re.sub(
                        r"(?:\n|^)(제\d+조(?:\s*의\s*\d+)?\s*[\(\（][^\)\\n]+[\)\）](?![에의을를은는이가과와]))",
                        r"\n### \1",
                        slice_content
                    )
                    # 서명 날인부 분리
                    slice_content = re.sub(
                        r"(?:\n|^)((?:원사업자와\s*수급사업자|발주자,\s*원사업자와\s*수급사업자|도급인과\s*수급인|사용자와\s*근로자)\s*는\s*이\s*계약의\s*성립을\s*증명하기\s*위하여)",
                        r"\n\n## 서명 날인\n\1",
                        slice_content
                    )

                    if suffix == "main":
                        target_path = output_path
                    else:
                        target_path = CONVERTED_DIR / f"{input_path.stem}_{suffix}.md"

                    with open(target_path, "w", encoding="utf-8") as wf:
                        wf.write(slice_content)

                logging.debug("💡 하도급 통합 마크다운 물리적 분할 및 정화 완료!")
            except Exception as pe:
                logging.warning(f"⚠️ 하도급 마크다운 분할 후처리 중 오류 발생: {pe}")
        else:
            # 하도급 계약서가 아닌 일반 계약서(근로, 도급)의 경우 기본 조항/서명 보정만 수행
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                fixed_content = re.sub(
                    r"(?:\n|^)(제\d+조(?:\s*의\s*\d+)?\s*[\(\（][^\)\\n]+[\)\）](?![에의을를은는이가과와]))",
                    r"\n### \1",
                    content
                )
                fixed_content = re.sub(
                    r"(?:\n|^)((?:원사업자와\s*수급사업자|발주자,\s*원사업자와\s*수급사업자|도급인과\s*수급인|사용자와\s*근로자)\s*는\s*이\s*계약의\s*성립을\s*증명하기\s*위하여)",
                    r"\n\n## 서명 날인\n\1",
                    fixed_content
                )
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)
                logging.debug("💡 일반 마크다운 조항 헤더 및 서명부 보정 완료!")
            except Exception as pe:
                logging.warning(f"⚠️ 일반 마크다운 후처리 보정 중 오류 발생: {pe}")

        logging.debug(f"✨ 변환 완료: {output_path}")
        return output_path
    else:
        raise RuntimeError(f"kordoc 변환 작업이 실패했습니다 (파일 미생성): {input_path.name}")

if __name__ == "__main__":
    # 스크립트 직접 실행 시 예시로 표준도급계약서 변환 테스트 수행
    try:
        for file in [
            RawContractFile.SI_SUBCONTRACT.value,
            RawContractFile.SW_EMPLOYMENT.value,
            RawContractFile.SW_FREELANCE.value,
            RawContractFile.SI_SUBCONTRACT_FULL.value,
            RawContractFile.SM_SUBCONTRACT.value,
            RawContractFile.SM_SUBCONTRACT_FULL.value,
        ]:
            convert_raw_to_markdown(file)
    except Exception as e:
        logging.error(f"❌ 변환 오류: {e}")
