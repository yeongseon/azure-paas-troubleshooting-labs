# Azure PaaS 트러블슈팅 실험실

[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-paas-troubleshooting-labs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read this in: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md)

**Azure App Service, Azure Functions, Azure Container Apps를 위한 서포트 엔지니어 스타일의 트러블슈팅 실험**

By Yeongseon Choe

---

## 이 프로젝트가 존재하는 이유

공식 Azure 문서는 정확하지만, 실제 지원 시나리오에서 나타나는 모든 엣지 케이스를 다루지는 않습니다. 일반적인 갭:

- **장애 모드 재현** — 문서에 설명된 것 이상으로 특정 장애 조건이 실제로 어떻게 나타나는지
- **플랫폼 vs 애플리케이션 경계** — 문제가 Azure 인프라에서 발생하는지 고객 애플리케이션 코드에서 발생하는지 판단
- **오해하기 쉬운 메트릭** — 한 가지 근본 원인을 암시하지만 실제로는 다른 것을 나타내는 신호
- **증거 보정** — 확신을 가지고 말할 수 있는 것과 추가 데이터가 필요한 것을 아는 것

이 저장소는 가설 기반 실험을 통해 이러한 갭을 채웁니다. 각 실험은 특정 시나리오를 재현하고, 관찰 결과를 기록하며, 명시적인 신뢰 수준으로 결과를 해석합니다.

이것은 실용 가이드가 아니고, 튜토리얼이 아니며, Microsoft Learn 대체물이 아닙니다.

## 다루는 내용

### App Service

- **메모리 압력** — Plan 수준 성능 저하, 스왑 스래싱, 커널 페이지 회수 효과
- **procfs 해석** — Linux 컨테이너 내부 /proc 데이터의 신뢰성과 한계
- **느린 요청** — 프론트엔드 타임아웃 vs 워커 측 지연 vs 종속성 지연
- **Zip Deploy vs Container** — 배포 방법 간 동작 차이

### Functions

- **Flex Consumption Storage** — 스토리지 ID 잘못된 구성 엣지 케이스
- **Cold Start** — 종속성 초기화, 호스트 시작 순서, 콜드 스타트 기간 분석
- **종속성 가시성** — 사용 가능한 텔레메트리를 통해 아웃바운드 종속성 동작을 관찰하는 한계

### Container Apps

- **Ingress SNI / Host Header** — SNI 및 호스트 헤더 라우팅 동작, 커스텀 도메인 엣지 케이스
- **Private Endpoint FQDN vs IP** — FQDN과 직접 IP 액세스 간의 동작 차이
- **Startup Probes** — startup, readiness, liveness 프로브 간의 상호작용

## 증거 모델

모든 실험은 보정된 증거 수준으로 결과에 태그를 붙입니다:

| 태그 | 의미 |
|-----|---------|
| **Observed** | 로그, 메트릭 또는 시스템 동작에서 직접 관찰됨 |
| **Measured** | 특정 값으로 정량적 확인됨 |
| **Correlated** | 두 신호가 함께 움직임; 인과관계는 미확립 |
| **Inferred** | 관찰에서 도출된 합리적 결론 |
| **Strongly Suggested** | 강력한 증거이지만 결정적이지 않음 |
| **Not Proven** | 가설이 테스트되었으나 확인되지 않음 |
| **Unknown** | 데이터 불충분 |

## 라이선스

MIT
