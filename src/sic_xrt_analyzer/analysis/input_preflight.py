"""Read-only presentation derived from original metadata and the adapter contract."""
import numpy as np

from .model_adapter import ModelInputContract


def channel_label(channels):
    return {1: "단일 채널", 3: "RGB", 4: "RGBA"}.get(channels, f"{channels}채널")


def input_descriptor(source):
    if source is None:
        return {}
    meta = source.metadata
    return {
        "dtype": meta.dtype, "bitDepth": meta.bit_depth, "channels": meta.channels,
        "colorMode": channel_label(meta.channels), "width": meta.width, "height": meta.height,
        "sourceKind": meta.format, "currentPage": source.page_index,
        "pageCount": meta.page_count, "sourceAvailable": True,
        "summary": f"{meta.bit_depth}비트 {channel_label(meta.channels)}",
    }


def contract_descriptor(adapter):
    contract = getattr(adapter, "input_contract", None)
    if not isinstance(contract, ModelInputContract):
        return {}
    bits = dict.fromkeys(1 if np.dtype(dtype).kind == "b" else np.dtype(dtype).itemsize * 8
                         for dtype in contract.accepted_dtypes)
    depths = " / ".join(f"{value}비트" for value in bits)
    channels = " / ".join(channel_label(value) for value in contract.expected_channels)
    manifest = getattr(getattr(adapter, "classifier", None), "manifest", {})
    contract_id = (f"{manifest['schema']} v{manifest['schema_version']}"
                   if "schema" in manifest and "schema_version" in manifest else "ModelInputContract")
    return {
        "contractId": contract_id, "acceptedDtypes": list(contract.accepted_dtypes),
        "expectedChannels": list(contract.expected_channels), "colorSpace": contract.color_space,
        "supportedScopes": [scope.value for scope in contract.supported_scopes],
        "inputSizePolicy": contract.input_size_policy, "normalization": contract.normalization,
        "bitDepthPolicy": contract.bit_depth_policy, "summary": f"{depths} {channels}",
    }


def input_preflight(adapter, source, *, waiting=False):
    """No I/O, inference, pixel buffer, conversion, request or mutable cached state."""
    expected = contract_descriptor(adapter)
    actual = input_descriptor(source) if not waiting else {}
    model_available = bool(adapter and adapter.available)
    if waiting or source is None:
        state, codes = "UNKNOWN", ["SOURCE_NOT_READY"]
    elif not model_available:
        state, codes = "UNKNOWN", ["MODEL_NOT_AVAILABLE"]
    elif not expected:
        state, codes = "ERROR", ["MODEL_CONTRACT_UNAVAILABLE"]
    else:
        codes = [code.value for code in adapter.input_contract.incompatibility_reasons(source.metadata)]
        state = "INCOMPATIBLE" if codes else "COMPATIBLE"
    messages = {
        "COMPATIBLE": "현재 입력은 모델의 입력 형식과 호환됩니다.",
        "INCOMPATIBLE": "현재 입력은 이 모델에서 지원하지 않습니다.",
        "ERROR": "모델 입력 계약을 확인할 수 없습니다.",
        "UNKNOWN": "이미지 준비가 끝나면 입력 호환성을 확인합니다." if codes == ["SOURCE_NOT_READY"]
                   else "모델을 연결하면 입력 호환성을 확인합니다.",
    }
    actual_summary = actual.get("summary", "입력 준비 중" if waiting else "원본 이미지 없음")
    expected_summary = expected.get("summary", "모델 입력 계약 확인 필요")
    actual_detail = (f"현재 입력: {actual_summary}\n형식: {actual['sourceKind']}\n"
                     f"dtype: {actual['dtype']} · 채널: {actual['channels']}\n"
                     f"크기: {actual['width']} × {actual['height']} px\n"
                     f"페이지: {actual['currentPage'] + 1} / {actual['pageCount']}" if actual else actual_summary)
    expected_detail = (f"입력 계약: {expected['contractId']}\n모델 요구: {expected_summary}\n"
                       f"dtype: {', '.join(expected['acceptedDtypes'])}\n"
                       f"채널: {', '.join(map(str, expected['expectedChannels']))}\n"
                       f"색상 정책: {expected['colorSpace']}\n"
                       f"크기 정책: {expected['inputSizePolicy']}\n"
                       f"정규화: {expected['normalization']}\n"
                       f"비트 정책: {expected['bitDepthPolicy']}" if expected else expected_summary)
    return {
        "state": state, "isCompatible": state == "COMPATIBLE", "reasonCodes": codes,
        "currentInput": actual, "modelExpected": expected,
        "currentInputSummary": actual_summary, "modelExpectedSummary": expected_summary,
        "message": messages[state], "currentInputDetail": actual_detail,
        "modelExpectedDetail": expected_detail,
        "accessibleSummary": f"{messages[state]} 현재 입력: {actual_summary}. 모델 요구: {expected_summary}.",
    }
