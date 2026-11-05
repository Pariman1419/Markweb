# Operational Guidelines & Rules

## Remote Server & Large File Downloads
- **Large File (>100MB) Policy**: Never initiate direct downloads of large files, PyTorch/CUDA wheels, or AI model weights exceeding 100MB directly on remote servers (e.g., A100 `10.151.28.9`) without prior user notification.
- **Transfer Strategy**: Always inform the user in advance so the asset can be downloaded rapidly on the dev workstation (`10.151.97.18`) and transferred to the target server via `scp`.
