#!/usr/bin/env python3
"""Run the free-llm-router proxy."""

import argparse
import logging

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="free-llm-router: rotate free LLM providers")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8686, help="Bind port (default: 8686)")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--log-level", default="info", help="Log level")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    
    # set config path in env so router can find it
    import os
    os.environ["FREEROUTER_CONFIG"] = args.config
    
    uvicorn.run(
        "free_llm_router.router:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
