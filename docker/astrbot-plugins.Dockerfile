FROM soulter/astrbot:v4.29.0

COPY requirements.runtime.txt /tmp/dfyqq-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dfyqq-requirements.txt \
    && rm -f /tmp/dfyqq-requirements.txt
