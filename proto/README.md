# Protobuf Encoding Notes

This project now encodes every enumerable field as a Protobuf `enum`.
Only the values of `description` and `item` stay unencoded and are kept in `retained_fields.json`.

The schema still models `description` and `item` explicitly through presence flags, so those fields remain part of the fixed Protobuf structure.

## Build

```bash
python3 -m grpc_tools.protoc -I./proto --python_out=./proto ./proto/message_fixed.proto
```

## Run

```bash
python3 proto/protobuf_mixed_encode.py
```

## Output

- `proto/out/fixed_fields.pb`: fixed fields only, with enum values stored as numeric protobuf fields
- `proto/out/retained_fields.json`: only `description` and `item` text values
- `proto/out/mixed_payload.pb`: protobuf container holding the fixed protobuf bytes plus retained JSON
