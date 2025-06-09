cat > layer_build/build_layer.sh <<'EOF'
#!/bin/bash

set -e

yum install -y python3.11 python3.11-devel gcc gcc-c++ \
    libffi-devel openssl-devel make zip

python3.11 -m ensurepip
python3.11 -m pip install --upgrade pip

mkdir -p /opt/python
pip3.11 install -r /layer/requirements.txt -t /opt/python

cd /opt && zip -r9 /layer/layer.zip python
EOF
