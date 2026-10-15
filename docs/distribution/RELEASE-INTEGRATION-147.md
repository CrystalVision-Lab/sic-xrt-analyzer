# 누적 변경 통합 및 0.6.0 배포 — #147

사용자 요청에 따라 열린 29개 PR의 커밋을 보존하여 main에 통합한다. 기존 28개 PR의 최종 CI는 모두 SUCCESS이며 #146과 통합 브랜치 CI는 배포 전에 확인한다.

## 포함 관계

| PR | head SHA | 연결 이슈 |
|---|---|---|
| #88 | `78ea12ba1e5f7e3e3634bf1af55fe4eb6faca535` | Closes #87 |
| #91 | `d88393933a014ad040c8573a3c54a959e2bc9b47` | Closes #90 |
| #93 | `0ae1a779625aa45ddce9059ccc4f3fffb7877da1` | Closes #92 |
| #95 | `243155a3dbf58d015eaf08cca2202bd2b7b9dab9` | Closes #94 |
| #97 | `a8ed31aceecd3c583d15bfac10c3010c70f75671` | Closes #96 |
| #99 | `cb8d43059f9929f3c3346f3eed2e37a8da80667b` | Closes #98 |
| #101 | `1afc4f73b0152a484fd31cd7cd56fadf62c72667` | Closes #100 |
| #103 | `15444dd7709bdc57972010f9633c14854e986dc4` | Closes #102 |
| #105 | `b3569b9e2e4958431f1e06f59792dc8aac25fb3d` | Closes #104 |
| #107 | `a6605088eb6cf54526da5d07f82a61433e83d926` | Closes #106 |
| #109 | `ab50c9a5a5c34050f8276eab65004f5cd10afeb2` | Closes #108 |
| #111 | `eed81c2898a3b9615130b989b7e4ed710918b0e9` | Closes #110 |
| #113 | `926a747c5f4ab7eb05b95efce93a6a66e7fc427e` | Closes #112 |
| #115 | `b39df05bbb8a50df3c6f8562664350095033affe` | Closes #114 |
| #117 | `84f9addc74549177f4b12b03b2406014b806b8a8` | Closes #116 |
| #119 | `e32376f04f91a954c86d95b22d45535316b2791b` | Closes #118 |
| #121 | `569d383310328d15a8a09a13c129a0b85b4e7c93` | Closes #120 |
| #124 | `517effebb87504fff8054030a5a437ec51f7c1d1` | Closes #122, Closes #123 |
| #126 | `676eb65adeb5b1b2a8ed18cc5460006512baf32f` | Closes #125 |
| #128 | `395d6de83c3e92dd1a7b7dd70557aebf935a436a` | Closes #127 |
| #130 | `4015a09ee1258d7fb1786a7e1f0c35b011830204` | Closes #129 |
| #132 | `46661e93cd2f39880fcc6134ccbda29c0c3a7534` | Closes #131 |
| #134 | `503746ba8255e54747bdcf779cf3be57e08e8786` | Closes #133 |
| #136 | `b61de26d2f7c948ee5c1d609f1a6f15914c389d4` | Closes #135 |
| #138 | `df127c98c999819ef4818348430c81b58e949ab0` | Closes #137 |
| #140 | `ed4f08802046e159b2391310e114146ea50dc159` | Closes #139 |
| #142 | `49b442b4afe19de2d0875c8cbbb3a6d8b8c67287` | Closes #141 |
| #144 | `d39ba6ad8ebc51fe47f3bbe52baf3384f7c3110d` | Closes #143 |
| #146 | `b473fcf7b9558c4b3638c229111be3434d08764d` | Closes #145 |

## 남기는 검증 과제

#49 검출/분류 정확도, #74 네이티브 파일창 원인 조사, #80 물리 마우스 Acceptance, #83 Qt 6.12 종료 안정성, #84 GPU/입력 성능, #87 수동 DPI/좌표 Acceptance, #89 실제 170% 확대 지연은 코드 통합만으로 완료 처리하지 않는다. #98의 BPD 실험 정확도, #116의 물리 웨이퍼 보정 및 #118의 실제 Z축/추적 품질도 기술 기능과 별도로 남긴다.

## 배포

0.6.0 BETA는 원본 해상도 캐시, 주변 결함 영역 검토와 전체 위치 지도, 신고 대기열·인증 수신, 곡선 추적 보정 및 업데이트 창을 포함한다. 실제 데이터와 모델은 Git/설치 파일/소스 패키지에서 제외한다. 기존 서버 데이터 및 이전 릴리스는 보존한다. `xrt_correction/v1` 신고는 UNVERIFIED이며 정답으로 자동 승인하지 않는다.

최종 CI, 백업, 설치 검증, 서버 및 공개 업데이트 전달 결과는 연결 PR/이슈에 기록한다.
