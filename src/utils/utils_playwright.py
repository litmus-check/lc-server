import asyncio
import textwrap
import os
import re
import traceback
from datetime import datetime
from log_config.logger import logger
from utils.utils_constants import *
from service.service_redis import add_log_to_redis, create_log_instruction_from_instruction_dict, store_browserbase_urls, get_browserbase_urls
from playwright.async_api import async_playwright, expect
from service.service_browserbase import get_browserbase_session, get_session_debug_urls

async def run_playwright_commands(playwright_instructions, trace_path, instructions, browser, testrun_id=None):
    logger.info(f"[{testrun_id}] Playwright instructions: {playwright_instructions}")
    try:
        async with async_playwright() as p:
            if browser == REMOTE_BROWSER_BASE:
                # Connect to the remote session
                logger.info(f"[{testrun_id}] Connecting to remote browserbase session, running test in script mode")
                try:
                    session = get_browserbase_session()
                    debug_urls = get_session_debug_urls(session.id)

                    # Store the full screen url in Redis
                    full_screen_url = debug_urls.pages[-1].debugger_fullscreen_url
                    store_browserbase_urls(f"{testrun_id}_live_stream", full_screen_url)
                    
                    # log debug URLs
                    logger.info(f"[{testrun_id}] Browserbase session ID: {session.id}")
                    logger.info(f"[{testrun_id}] Browserbase debug URLs: {debug_urls}")
                    
                    chromium = p.chromium
                    browser = await chromium.connect_over_cdp(session.connect_url)
                    context = browser.contexts[0]
                    
                    
                except Exception as e:
                    logger.debug(traceback.format_exc())
                    logger.error(f"[{testrun_id}] Unable to get browserbase session, launching local browser" + str(e))
                    browser = await p.chromium.launch(headless=os.getenv('RUN_TEST_HEADLESS', 'True').lower() == 'true')
                    context = await browser.new_context()
                            
            else:
                logger.info(f"[{testrun_id}] Launching local browser, running test in script mode")
                browser = await p.chromium.launch(headless=os.getenv('RUN_TEST_HEADLESS', 'True').lower() == 'true')
                context = await browser.new_context()
            
            # Start tracing
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)

            page = await context.new_page()

            local_vars = {
                "browser": browser,
                "context": context,
                "page": page,
                "asyncio": asyncio,
                "logger": logger,
                "add_log_to_redis": add_log_to_redis,
                "testrun_id": testrun_id,
                "datetime": datetime,
                "expect": expect,
                "re": re
            }

            # Build dynamic function
            script = "async def _temp_func(context, browser, page, asyncio, logger, add_log_to_redis, testrun_id, datetime, expect, re):\n"

            for index, playwright_commands in playwright_instructions.items():
                instruction_text = instructions[int(index)]
                logger.info(f"[{testrun_id}] Processing instruction group {int(index)+1}: {instruction_text}")
                instruction = create_log_instruction_from_instruction_dict(instruction_text)
                # start tracing group
                start_group = f'''
                try:
                    await page.context.tracing.group({repr(instruction)})
                except Exception as e:
                    logger.info("Error while starting tracing group")
                '''
                script += textwrap.indent(textwrap.dedent(start_group), "    ")
                # script += f'''    await page.context.tracing.group({repr(instruction_text)})\n'''
                script += f'''    logger.info({repr(f"Started Executing Instruction '{instruction_text}'")})\n'''
                script += f'''    add_log_to_redis(testrun_id, {{
                    "info": {repr(f"Started Executing Instruction '{instruction}'")},
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                }})\n'''

                if not playwright_commands:
                    script += "    pass\n"
                else:
                    for line_no, cmd in enumerate(playwright_commands):
                        clean_cmd = textwrap.dedent(cmd.replace("\t", "    ")).strip()

                        # Add logging before and after command inside script
                        script += f"    logger.info({repr(f'Executing line {line_no+1}: {cmd}').strip()})\n"

                        script += f'''    add_log_to_redis(testrun_id, {{
                            "info": {repr(f"Executing command: {cmd}")},
                            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        }})\n'''

                        script += textwrap.indent(clean_cmd, "    ") + "\n"

                        script += f'''    add_log_to_redis(testrun_id, {{
                            "info": {repr(f"Executed command: {cmd}")},
                            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        }})\n'''
                
                # end tracing group in try catch block
                close_group= '''    
                try:
                    await page.context.tracing.group_end()
                except Exception as e:
                    logger.info(f"Error while stopping tracing")\n'''
                script += textwrap.indent(textwrap.dedent(close_group), "    ")

                # Add log to redis
                script += f'''    add_log_to_redis(testrun_id, {{
                    "info": {repr(f"Finished Executing Instruction '{instruction}'")},
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                }})\n'''

            try:
                logger.debug(f"[{testrun_id}] Script: {script}")
                exec(script, {}, local_vars)
                await local_vars["_temp_func"](context, browser, page, asyncio, logger, add_log_to_redis, testrun_id, datetime, expect, re)
                # Add log to redis
                add_log_to_redis(testrun_id, {
                    "info": "All instructions executed successfully",
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                })

            except Exception as e:
                add_log_to_redis(testrun_id, {
                    "error": f"Error while executing playwright instructions: {e}",
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                })
                logger.error(f"[{testrun_id}] Error while executing playwright instructions: {e}")
                logger.debug(traceback.format_exc())
                raise e
            finally:
                try:
                    await context.tracing.stop(path=trace_path)
                except Exception as e:
                    logger.error(f"[{testrun_id}] Error while stopping tracing: {e}")
                    logger.debug(traceback.format_exc())
                try:
                    await browser.close()
                except Exception as e:
                    logger.error(f"[{testrun_id}] Error while closing browser: {e}")
                    logger.debug(traceback.format_exc())
    except Exception as e:
        logger.error(f"[{testrun_id}] An error occurred while running Playwright commands: {e}")
        logger.debug(traceback.format_exc())     
        raise e