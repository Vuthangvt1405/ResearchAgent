# Kernel image for project notebooks (plan §4.1, AC19).
# Build: docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker
FROM python:3.12-slim

# Kernel packages live in kernel-requirements.txt (next to this file)
COPY kernel-requirements.txt /tmp/kernel-requirements.txt
RUN pip install --no-cache-dir -r /tmp/kernel-requirements.txt \
    && rm /tmp/kernel-requirements.txt \
    && useradd --uid 1000 --create-home kernel

# Charts render to PNG without a display. The root filesystem is read-only,
# so everything IPython, Jupyter and matplotlib write goes to /tmp (a tmpfs).
ENV MPLBACKEND=module://matplotlib_inline.backend_inline \
    MPLCONFIGDIR=/tmp/matplotlib \
    IPYTHONDIR=/tmp/ipython \
    JUPYTER_RUNTIME_DIR=/tmp/jupyter/runtime \
    JUPYTER_DATA_DIR=/tmp/jupyter/data \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1

USER 1000
WORKDIR /work
# The app passes: python -m ipykernel_launcher -f /conn/kernel.json
