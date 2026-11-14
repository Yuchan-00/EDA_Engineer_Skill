<div align="center">

# EDA Engineer Skill

**AI 에이전트를 위한 검증 우선 전자회로 설계**

[![License: MIT + Commons Clause](https://img.shields.io/badge/license-MIT%20%2B%20Commons%20Clause-blue)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](.agents/skills/eda-engineer/SKILL.md)
[![Hosts](https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex-555)](#지원-호스트)
[![Status](https://img.shields.io/badge/status-first%20draft-orange)](#현재-상태)

[스킬](.agents/skills/eda-engineer/SKILL.md) / [파이프라인](.agents/skills/eda-engineer/references/pipeline.md) / [답변 키](.agents/skills/eda-engineer/references/answers.md) / [English](README.md)

</div>

`eda-engineer` 스킬은 AI 에이전트가 AI EDA Engineer 참고 시스템의 `ai-eda` CLI로 작은 전자회로를 설계·시뮬레이션·검사하게
합니다 — KiCad 회로도와 PCB, ngspice 시뮬레이션, ERC/DRC, BOM/CPL, 독립 검토까지. 모든 숫자에는 출처가 있고, 모든 판정은
도구가 내리며, "확인하지 못함"은 그 자체로 하나의 상태입니다.

## 빠른 시작

에이전트가 스킬을 읽는 폴더로 복사합니다:

```bash
# Claude Code
cp -r .claude/skills/eda-engineer <your-project>/.claude/skills/
# Codex (그리고 Agent Skills를 읽는 다른 호스트)
cp -r .agents/skills/eda-engineer <your-project>/.agents/skills/
```

- 스킬은 `ai-eda` CLI를 움직입니다. 먼저 [AI EDA Engineer](https://github.com/Yuchan-00/AI_EDA_Engineer) 참고 시스템을 설치하세요([스킬이 기대하는 것](.agents/skills/eda-engineer/SKILL.md)).
- ERC / DRC에는 `kicad-cli`(KiCad 10 이상), SPICE에는 공유 ngspice 라이브러리가 필요합니다([자세히](.agents/skills/eda-engineer/references/pipeline.md)).
- CLI가 없을 때: [CLI 없이 하는 법](.agents/skills/eda-engineer/references/without-cli.md).

그다음 평소 말로 요청하면 됩니다 — "12 V를 5 V로 나누는 분배기 설계해 줘", "design a divider". 스킬이 실제로 실행하는 명령:

```bash
ai-eda new divider --dir ./divider --request "12 V to 5 V unloaded divider"
ai-eda run ./divider/ir.json --answer application="bench reference" --answer jurisdiction=EU \
  --answer input_voltage="12 V" --answer output_voltage="5 V" --no-pdf      # 설계 표에서 멈춤
ai-eda run ./divider/ir.json --answer confirm_design=yes --no-pdf            # 사용자가 확인한 뒤에만
ai-eda stage-reports ./divider/ir.json && ai-eda report ./divider/ir.json
python <skill>/scripts/deliver.py ./divider --lang ko                       # PDF 보고서 두 개 + zip 하나
```

## 설명

- 요구사항에서 KiCad 프로젝트까지, 확인 한 번: 템플릿 또는 설계 파일(`ai-eda run --design FILE.json`)을 표로 보여 주고, 확인하기 전에는 설계에 아무것도 넣지 않습니다.
- 살 수 있는 부품값: 저항·커패시터·인덕터는 IEC 60063 E 계열 값으로 놓고 그 값으로 회로를 판정합니다.
- 기대값을 적은 ngspice 시뮬레이션, 보고서에 파형.
- ERC와 DRC는 모델이 아니라 `kicad-cli`가 판정합니다.
- 참고 시스템의 결정론적 배치·배선, 모든 트랙과 비아를 그 규칙까지 추적.
- 결과 전달: 요약 보고서와 상세 보고서(PDF, 한국어 또는 영어), KiCad 프로젝트·Gerber·드릴·BOM·CPL·보고서를 묶은 zip 하나.
- 넘지 않는 선: 에이전트가 스스로 설치·구매·업로드·푸시하지 않음, 사용자 대신 설계를 확인하지 않음, 부품 사실은 기억이 아니라 제조사 데이터시트에서.

## 지원 호스트

| 호스트 | 스킬 폴더 | 비고 |
|---|---|---|
| Claude Code | `.claude/skills/eda-engineer/` | `.agents` 폴더와 바이트 동일한 사본 |
| Codex | `.agents/skills/eda-engineer/` | Codex 전용 메타데이터 `agents/openai.yaml` |
| 그 밖의 Agent Skills 호스트 | `.agents/skills/eda-engineer/` | 설명문으로 `SKILL.md`를 불러옴 |

발동 시험(2026-11): Claude Code 양성 10/10, 음성 5/5; Codex 양성 10/10, 음성 4/5.

## 현재 상태

| 영역 | 상태 (2026-11-15) |
|---|---|
| 스킬 | 초안, 참고 코드와 두 번 대조 |
| 결과 보고서와 zip | 동작 |
| 표준 부품값(E 계열) | 템플릿 6종과 설계 파일; `lc_lowpass`, `astable`, 무전기 계열 남음 |
| 미세 피치 탈출(0.5 mm QFP) | 비아 팬아웃(`routing.maze` 0.8)으로 LQFP-100 패드 99개 모두 탈출 |
| 다층 배선(4–12층, 블라인드·베리드·마이크로 비아) | 참고 시스템 로컬 브랜치에 구현: 비아 종류, 6–12층 적층, N층 배선기, 층 상승 2 → 4 → 6 → 8 → 10 → 12; STM32 시험 보드는 6층에서 91개 넷 모두 배선 |
| PCB 재료(FR-4, Rogers RO4350B, 폴리이미드 플렉스, 알루미늄 IMS) | 장치 요구에서 제안, 수치는 제조사 데이터시트, 사용자가 확인 |
| LLM 공급자(Claude Code, Codex, OpenAI 호환, 교차 확인) | CLI는 구독 로그인에서만, 예산을 주지 않으면 API 요금 없음 |
| STM32F407 디스플레이 시험 보드 | 6층, 91개 넷 모두 배선; KiCad DRC 오류 0 / 미연결 0, ERC 0 / 0, 시뮬레이션 통과 |
| 무전기 송수신기(부품 441개) | DRC FAIL(오류 67건), 원인 미조사 |

참고 시스템의 개선은 그 레포의 로컬 브랜치 `work/ead-skill`에 있고 아직 업스트림에 올리지 않았습니다.

## 문서

#### 스킬

- [SKILL.md](.agents/skills/eda-engineer/SKILL.md) - 에이전트가 할 수 있는 것과 없는 것, 기본 흐름
- [references/pipeline.md](.agents/skills/eda-engineer/references/pipeline.md) - 단계, 상태, 종료 코드, 외부 행위
- [references/answers.md](.agents/skills/eda-engineer/references/answers.md) - `--answer` 답변 키
- [references/without-cli.md](.agents/skills/eda-engineer/references/without-cli.md) - CLI 없이 할 일
- [scripts/deliver.py](.agents/skills/eda-engineer/scripts/deliver.py) - 실행 끝의 보고서와 zip

#### 도구

- [tools/check_skill_portable.py](tools/check_skill_portable.py) - 이식성 검사(`--sync`가 `.claude` 사본을 맞춤)
- [tools/check_report.py](tools/check_report.py) - 보고서에 약속한 절 제목이 있는지 검사
- [tests/](tests/) - 도구와 `deliver.py`의 테스트(`python -m pytest tests -q`)

## 기여

- `.agents/skills/eda-engineer/`와 `.claude/skills/eda-engineer/`를 같게 유지하세요: `python tools/check_skill_portable.py --sync`.
- "측정함"이라는 주장에는 명령·버전·결과의 기록이 있어야 합니다.
- 부품 사실(핀 배치, 핀 기능, 정격)은 기억이 아니라 제조사 데이터시트에서 읽고 출처를 적습니다.
- 테스트를 통과시키려고 허용 오차를 넓히지 않습니다.

## 감사의 말

- [AI EDA Engineer](https://github.com/Yuchan-00/AI_EDA_Engineer) 참고 시스템 - 스킬이 움직이는 `ai-eda` CLI (MIT + Commons Clause)
- [KiCad](https://www.kicad.org/) - 회로도, PCB, ERC, DRC, Gerber 출력, 외부 도구로 실행 (GPL-3.0-or-later)
- [ngspice](https://ngspice.sourceforge.io/) - 회로 시뮬레이션, 공유 라이브러리로 불러옴 (라이선스는 그 프로젝트 참조)
- [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy), [fxp/ee-skills](https://github.com/fxp/ee-skills) - 구조와 방법의 참고로만 읽음, 파일 복사 없음 (MIT; [NOTICE](NOTICE) 참조)

## 라이선스

MIT License + Commons Clause([LICENSE](LICENSE), 영문이 우선): 무료로 사용·복제·수정·공유할 수 있고 자기 에이전트에 스킬을 불러와 써도 됩니다. 다만 이 소프트웨어 자체, 또는 그 가치가 주로 이 소프트웨어에서 나오는 제품·서비스는 별도 합의 없이 팔 수 없습니다. 소스 공개 소프트웨어이며 OSI 오픈 소스는 아닙니다. 이 레포는 Agent Skill이고 MCP 서버가 아닙니다. 제3자 목록에 올라온 것은 저자가 만든 것이 아닙니다.

Copyright (c) 2026 Yuchan ([github.com/Yuchan-00](https://github.com/Yuchan-00)).
