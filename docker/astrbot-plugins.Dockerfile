FROM soulter/astrbot:v4.29.0

ARG SHOPPING_MCP_COMMIT=22190059ea1007050e2d0864e9afed3d05bd19c9
ARG NAVER_MCP_COMMIT=f5ae4b12ac24c023aa6d0841fed9867a88eb8501
ARG BUYWHERE_MCP_VERSION=0.4.0

COPY requirements.runtime.txt /tmp/dfyqq-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dfyqq-requirements.txt \
    && rm -f /tmp/dfyqq-requirements.txt

# Read-only MCP integrations. Sources and package versions are pinned so a
# container rebuild cannot silently pick up upstream changes.
RUN git clone --filter=blob:none --no-checkout \
        https://github.com/EastMG/dsh-shopping-mcp.git /opt/dfyqq-mcp/china-shopping \
    && git -C /opt/dfyqq-mcp/china-shopping checkout --detach "$SHOPPING_MCP_COMMIT" \
    && git clone --filter=blob:none --no-checkout \
        https://github.com/uju777/mcp-server-naver-search.git /opt/dfyqq-mcp/naver-search \
    && git -C /opt/dfyqq-mcp/naver-search checkout --detach "$NAVER_MCP_COMMIT" \
    && pip install --no-cache-dir /opt/dfyqq-mcp/china-shopping \
        -r /opt/dfyqq-mcp/naver-search/requirements.txt \
    && rm -rf /opt/dfyqq-mcp/china-shopping/.git /opt/dfyqq-mcp/naver-search/.git

RUN npm install --global --omit=dev --no-audit --no-fund \
        "@buywhere/mcp-server@$BUYWHERE_MCP_VERSION"
