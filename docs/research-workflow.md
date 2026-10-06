# 고정 모델로 Jupyter 분석·전후 추적

이 기능은 연구용 분석입니다. 새 학습을 실행하지 않으며 기존 GUI 분석 파이프라인과 독립적입니다.
`pip install .[research]`로 설치한 패키지를 Jupyter 커널에서 사용합니다.
`notebooks/06_research_analysis.ipynb`와 로컬 설정 JSON을 작업 폴더에 놓고 전체 실행하면 입력 화면이 나타납니다.

## 입력과 출력

- 영상: 단일 uint8 RGB TIFF/PNG/JPEG, 또는 `archive.zip::member.tif`. ZIP은 메모리에서 읽으며 추출하지 않습니다.
- 기존 좌표 CSV: `point_id,x,y`. 좌표는 원본 영상의 0 기반 픽셀 좌표입니다. 제공 라벨은 추론 입력이 아닙니다.
- 자동 후보: 원해상도에서 밝고 어두운 국소 대비 극점을 찾습니다. 이것은 학습된 결함 검출기가 아닙니다.
  약한 결함·긴 BPD를 놓치거나 하나의 결함을 여러 번 찾을 수 있습니다. 후보 상한 도달 여부를 기록합니다.
- 분류: 실제 중심 좌표 주변 128×128 RGB 패치. 경계 패치는 패딩하지 않고 제외 목록에 기록합니다.
  같은 반올림 중심은 중복 제외합니다. 점수는 보정된 확률/정답 신뢰도가 아닙니다.
- 결과: 실행별 새 폴더에 `result.json`, `predictions.csv`, `excluded_points.csv`, `overlay.png`.
  종류별 수는 분류한 **후보 수**입니다. 실제 전체 결함 수로 해석하지 않습니다.
- 추적: `matches.csv`, `result.json`, 정렬 성공 시 `aligned_overlay.png`, `tracking_overlay.png`.
  회색/색상 원본은 그대로 보존하며 출력은 별도 폴더에 저장합니다.

## 모델 계약

ML 저장소가 내보낸 `frozen_xrt_patch_classifier` 버전 1의 `manifest.json`/`model.onnx`를 소비합니다.
스키마, RGB 입력 모양·정규화, 클래스 순서(BPD,TED,TSD), 상태, SHA-256이 다르면 중단합니다.
연구용 export 검증은 물리적 정답이나 운영 배포 승인이 아닙니다. 다른 저장소 소스는 import하지 않습니다.
검출기·배경 클래스·TED 방향 a–f·TSD 세부형은 이 모델에 없습니다.

## 전후 정렬과 연결

미리보기 SIFT 특징점 → 양방향 Lowe ratio 0.75 → RANSAC homography를 사용합니다.
[OpenCV의 SIFT와 homography 예제](https://docs.opencv.org/3.0-last-rst/doc/py_tutorials/py_feature2d/py_feature_homography/py_feature_homography.html)를 따른 구현입니다.
미리보기의 실제 가로·세로 배율을 각각 원본 좌표로 환산합니다. 변환 방향은 **후 → 전**입니다.
최소 12 inlier, 비율 0.4, 재투영 오차, 겹침 면적, 지지점 분포, 변환의 유효성을 확인합니다.
모든 품질 기준을 통과해야 `accepted_tentative`로 기록하며, 실패하면 연결 CSV는 비어 있습니다.
이 값은 검증된 정렬 정확도가 아니므로 정렬 그림을 함께 확인해야 합니다.

자동 정렬 실패 시 `before_x,before_y,after_x,after_y` 열을 가진 대응점 CSV를 입력할 수 있습니다.
영상 전체에 분산된 최소 6쌍이 필요합니다. 대응점이 사용자 제공이라는 사실만으로 인간 검수 완료를 기록하지 않습니다.
좌표는 원본 픽셀입니다. TIFF 배율/스케일바만 추측하여 µm로 바꾸지 않습니다.

공통 촬영 영역의 점 중, 지정 반경 안에서 서로 가능한 상대가 정확히 하나씩인 경우만 잠정 연결합니다.
종류를 연결 조건으로 사용하지 않습니다. 여러 상대가 가능하면 `ambiguous`, 상대가 없으면 `unmatched`,
겹침 밖이면 `outside_overlap`입니다. 미연결을 생성·소멸로 판정하지 않습니다.
`type_change_candidate`는 예측 종류가 바뀐 잠정 연결입니다. BPD→TED의 물리적 전환율을 계산하지 않습니다.

## 로컬 설정 예시

`research_analysis.local.json` (Git에 넣지 않음):

```json
{
  "bundle": "C:/local/frozen_model",
  "output_root": "C:/local/analysis_results",
  "before_image": "C:/local/before.tif",
  "after_image": "C:/local/after.tif",
  "before_points": "C:/local/before_points.csv",
  "after_points": "C:/local/after_points.csv",
  "before_result": "",
  "after_result": "",
  "landmarks_csv": ""
}
```

실제 데이터와 결과는 Git에 넣지 않습니다. 원본과 사람의 검수 기록을 수정하지 않습니다.

## 검증 기록 (2026-10-06)

- Windows에서 연구 기능 11개 테스트 포함, ImageJ를 제외한 121개와 ImageJ 모듈 13개를 각각 통과했습니다.
  Qt·JVM 전체를 한 프로세스에 합친 검사에서는 기존 QML 정리 단계의 access violation이 발생하여
  두 프로세스로 분리해 검증했습니다. 이 실행상 제약은 연구 노트북의 ONNX·OpenCV 처리와 별개입니다.
- 실제 1번 웨이퍼의 제공 좌표: 전 1,929개, 후 2,320개 분류. 경계·중복 등 제외 항목을 별도 저장했습니다.
- SIFT 고유 대응점 34쌍 중 28 inlier, 이 지지점의 재투영 잔차 중앙값 약 1.70 원본 픽셀.
  이 수치는 독립적인 정렬 정확도 평가가 아닙니다.
- 연결 반경 25 원본 픽셀에서 잠정 연결 1,683쌍, 예측 종류 변화 후보 35쌍.
  전후 원본 패치 예시를 함께 저장했습니다. 정답 대응 관계는 아직 확인되지 않았습니다.
- Jupyter 노트북의 모든 셀을 실행하여 입력 화면과 저장 결과 표시를 확인했습니다.
  자동 후보 검출의 정확도, 세부형, 물리적 전환, 3D는 이 검증 결과에 포함하지 않습니다.
