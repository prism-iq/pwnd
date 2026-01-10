#!/usr/bin/env python3
"""
L Investigation - Discord Bot
Polyglot architecture integration for Discord
"""

import os
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import json
import time

# =============================================================================
# Configuration
# =============================================================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')
GUILD_ID = os.getenv('DISCORD_GUILD_ID', '')

# Polyglot organs
ORGANS = {
    'brain': os.getenv('BRAIN_URL', 'http://127.0.0.1:8085'),
    'cells': os.getenv('CELLS_URL', 'http://127.0.0.1:9001'),
    'veins': os.getenv('VEINS_URL', 'http://127.0.0.1:8002'),
    'lungs': os.getenv('LUNGS_URL', 'http://127.0.0.1:3000'),
}

# =============================================================================
# Bot Setup
# =============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!l ', intents=intents)

# =============================================================================
# Organ Communication
# =============================================================================

async def call_organ(organ: str, path: str, data: dict = None, method: str = 'POST') -> dict:
    """Call a polyglot organ service"""
    url = f"{ORGANS[organ]}{path}"

    async with aiohttp.ClientSession() as session:
        try:
            if method == 'GET':
                async with session.get(url, timeout=30) as resp:
                    return await resp.json()
            else:
                async with session.post(url, json=data, timeout=30) as resp:
                    return await resp.json()
        except Exception as e:
            return {'error': str(e), 'organ': organ}

async def investigate(query: str, session_id: str = None) -> dict:
    """Run full investigation through polyglot pipeline"""

    # Phase 1: Brain analyzes query
    strategy = await call_organ('brain', '/analyze', {'query': query})

    # Phase 2: Parallel extraction and search
    extract_task = call_organ('cells', '/extract', {'text': query})

    entities, = await asyncio.gather(extract_task)

    # Phase 3: Get brain to coordinate investigation
    result = await call_organ('brain', '/investigate', {
        'query': query,
        'sessionId': session_id or f'discord-{int(time.time())}'
    })

    return {
        'strategy': strategy,
        'entities': entities,
        'result': result
    }

# =============================================================================
# Discord Events
# =============================================================================

@bot.event
async def on_ready():
    print(f'╔{"═" * 50}╗')
    print(f'║  L Investigation Discord Bot                     ║')
    print(f'║  Logged in as {bot.user.name:<35} ║')
    print(f'╠{"═" * 50}╣')
    print(f'║  Commands:                                       ║')
    print(f'║    /investigate <query>  - Run investigation     ║')
    print(f'║    /extract <text>       - Extract entities      ║')
    print(f'║    /health               - Check organ status    ║')
    print(f'╚{"═" * 50}╝')

    # Sync slash commands
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')

# =============================================================================
# Slash Commands
# =============================================================================

@bot.tree.command(name='investigate', description='Run an OSINT investigation')
@app_commands.describe(query='Your investigation query')
async def cmd_investigate(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)

    start = time.time()
    result = await investigate(query, f'discord-{interaction.user.id}')
    elapsed = time.time() - start

    # Build response embed
    embed = discord.Embed(
        title='Investigation Results',
        description=query[:200],
        color=discord.Color.green() if not result.get('error') else discord.Color.red()
    )

    # Strategy
    strategy = result.get('strategy', {})
    if strategy and not strategy.get('error'):
        embed.add_field(
            name='Strategy',
            value=f"Priority: **{strategy.get('priority', 'normal')}**\nConfidence: {strategy.get('confidence', 0):.0%}",
            inline=True
        )

    # Entities
    entities = result.get('entities', {})
    if entities and not entities.get('error'):
        entity_counts = []
        for key in ['persons', 'dates', 'emails', 'amounts']:
            count = len(entities.get(key, []))
            if count:
                entity_counts.append(f"{key}: {count}")
        if entity_counts:
            embed.add_field(name='Entities Found', value='\n'.join(entity_counts), inline=True)

    # Investigation result
    inv_result = result.get('result', {})
    if inv_result.get('success'):
        embed.add_field(
            name='Status',
            value=f"Session: `{inv_result.get('sessionId', 'N/A')[:20]}`",
            inline=False
        )

    embed.set_footer(text=f'Completed in {elapsed:.2f}s | L Investigation Polyglot')

    await interaction.followup.send(embed=embed)

@bot.tree.command(name='extract', description='Extract entities from text')
@app_commands.describe(text='Text to analyze')
async def cmd_extract(interaction: discord.Interaction, text: str):
    await interaction.response.defer(thinking=True)

    start = time.time()
    result = await call_organ('cells', '/extract', {'text': text})
    elapsed = time.time() - start

    embed = discord.Embed(
        title='Entity Extraction',
        description=text[:200] + ('...' if len(text) > 200 else ''),
        color=discord.Color.blue()
    )

    if not result.get('error'):
        for key in ['persons', 'dates', 'emails', 'amounts', 'organizations']:
            items = result.get(key, [])
            if items:
                values = [item.get('value', item.get('name', str(item)))[:50] for item in items[:5]]
                embed.add_field(name=key.title(), value='\n'.join(values) or 'None', inline=True)

        embed.add_field(
            name='Processing',
            value=f"Rust: {result.get('processing_time_ms', 0)}ms\nTotal: {elapsed*1000:.1f}ms",
            inline=False
        )
    else:
        embed.add_field(name='Error', value=result.get('error', 'Unknown error'), inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name='health', description='Check polyglot organ status')
async def cmd_health(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    embed = discord.Embed(
        title='Polyglot Organ Status',
        color=discord.Color.gold()
    )

    # Check each organ
    for name, url in ORGANS.items():
        try:
            result = await call_organ(name, '/health', method='GET')
            status = result.get('status', 'unknown')

            if status in ['healthy', 'thinking', 'breathing']:
                emoji = '🟢'
                status_text = f"**{status}**"
            else:
                emoji = '🟡'
                status_text = f"{status}"

            # Add metrics if available
            metrics = result.get('metrics', {})
            if metrics:
                details = []
                if 'thoughts' in metrics:
                    details.append(f"Thoughts: {metrics['thoughts']}")
                if 'inhales' in metrics:
                    details.append(f"Inhales: {metrics['inhales']}")
                status_text += '\n' + '\n'.join(details) if details else ''

        except Exception as e:
            emoji = '🔴'
            status_text = f"**offline**\n{str(e)[:50]}"

        embed.add_field(name=f'{emoji} {name.title()}', value=status_text, inline=True)

    embed.set_footer(text='L Investigation Polyglot Architecture')
    await interaction.followup.send(embed=embed)

# =============================================================================
# Text Commands (Legacy)
# =============================================================================

@bot.command(name='search')
async def text_search(ctx, *, query: str):
    """Legacy text command for search"""
    async with ctx.typing():
        result = await investigate(query)

        response = f"**Investigation:** {query[:100]}\n"

        strategy = result.get('strategy', {})
        if strategy:
            response += f"Priority: {strategy.get('priority', 'normal')}\n"

        entities = result.get('entities', {})
        if entities:
            counts = [f"{k}: {len(v)}" for k, v in entities.items() if v and k != 'error']
            if counts:
                response += f"Entities: {', '.join(counts)}\n"

        await ctx.send(response[:2000])

# =============================================================================
# Main
# =============================================================================

def main():
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN not set")
        print("Set it in .env or environment:")
        print("  export DISCORD_TOKEN='your-bot-token'")
        return

    print("Starting L Investigation Discord Bot...")
    bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
    main()
