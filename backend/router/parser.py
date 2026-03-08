import msgpack
from pydantic import TypeAdapter
from shared.schemas import WsClientPayload, WsServerPayload

_client_payload_adapter = TypeAdapter(WsClientPayload)

def parse_client_payload(raw_bytes: bytes) -> WsClientPayload:
    # Decode string as utf-8, but keep bytes untouched
    data = msgpack.unpackb(raw_bytes, raw=False)
    return _client_payload_adapter.validate_python(data)

def serialize_server_payload(payload: WsServerPayload) -> bytes:
    # Pydantic V2 dump
    data_dict = payload.model_dump()
    return msgpack.packb(data_dict, use_bin_type=True)
