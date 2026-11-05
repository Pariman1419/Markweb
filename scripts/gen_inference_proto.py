"""Generate gRPC and protobuf code from proto definition."""
import re
from pathlib import Path
from grpc_tools import protoc

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = REPO_ROOT / "services" / "inference" / "proto"
OUT_DIR = REPO_ROOT / "services" / "inference"
PROTO_FILE = PROTO_DIR / "mark_inference.proto"


def main():
    args = [
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        str(PROTO_FILE),
    ]
    exit_code = protoc.main(args)
    if exit_code != 0:
        raise RuntimeError(f"protoc failed with exit code {exit_code}")

    # Fix relative import in generated grpc file so it works in both package and standalone mode
    grpc_file = OUT_DIR / "mark_inference_pb2_grpc.py"
    if grpc_file.is_file():
        content = grpc_file.read_text(encoding="utf-8")
        patched = re.sub(
            r"^import mark_inference_pb2 as mark__inference__pb2",
            "try:\n    from services.inference import mark_inference_pb2 as mark__inference__pb2\nexcept ImportError:\n    import mark_inference_pb2 as mark__inference__pb2",
            content,
            flags=re.MULTILINE,
        )
        grpc_file.write_text(patched, encoding="utf-8")
    print(f"Generated proto files in {OUT_DIR}")


if __name__ == "__main__":
    main()
