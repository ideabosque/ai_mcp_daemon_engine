#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List

import uvicorn
from pyngrok import ngrok

from .handlers.config import Config
from .handlers.mcp_server_app import app, run_stdio


class AIMCPDaemonEngine(object):
    def __init__(self, logger: logging.Logger, **setting: Dict[str, Any]) -> None:

        # Initialize configuration via the Config class
        Config.initialize(logger, **setting)

        self.transport = setting["transport"]
        self.port = setting["port"]
        self.use_ngrok = setting.get("use_ngrok", "False") == "True"
        self.ngrok_authtoken = setting.get("ngrok_authtoken", None)
        self.logger = logger

    def run(self):
        try:
            if self.transport == "sse":
                self.logger.info("Running in SSE mode...")
                self.run_sse()
            else:
                self.logger.info("Running in stdio mode...")
                asyncio.run(self.run_stdio())
        except KeyboardInterrupt:
            self.logger.info("Daemon interrupted by user.")
        except Exception as e:
            self.logger.exception("Fatal daemon error")
            sys.exit(1)

    def run_sse(self):
        """Run SSE server using uvicorn."""
        public_url = None
        if self.use_ngrok and self.ngrok_authtoken:
            public_url = ngrok.connect(self.port, bind_tls=True).public_url
            self.logger.info(
                f"🔗  ngrok tunnel open at {public_url} → http://127.0.0.1:{self.port}"
            )

        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=self.port,
            log_level="info",
            access_log=True,
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())

    async def run_stdio(self):
        """Delegate to the external stdio runner."""
        await run_stdio(self.logger)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger()

    daemon = AIMCPDaemonEngine(
        logger,
        **{
            "transport": os.getenv("MCP_TRANSPORT", "sse").lower(),
            "port": int(os.getenv("PORT", "8000")),
            "mcp_configuration": (
                json.load(
                    open(
                        os.getenv("MCP_CONFIG_FILE"),
                        "r",
                    )
                )
                if os.getenv("MCP_CONFIG_FILE")
                else None
            ),
            "region_name": os.getenv("REGION_NAME"),
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "use_ngrok": os.getenv("USE_NGROK", "False"),
            "ngrok_authtoken": os.getenv("NGROK_AUTHTOKEN", None),
        },
    )
    daemon.run()
