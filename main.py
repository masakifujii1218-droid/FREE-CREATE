import sys
import site
import os

# Renderが実際にインストールしたライブラリの隠し場所を自動取得して最優先で追加
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.insert(0, user_site)

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
from PIL import Image, ImageDraw
import io
from flask import Flask
from threading import Thread

# ==========================================
# 🌐 Renderのポートチェック回避用 Webサーバー
# ==========================================
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    # Renderは標準でPORT環境変数を提供しているので、それを使用（なければ8080）
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ==========================================
# ⚙️ インテントの設定（Message Contentを強制オン）
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True

class DiaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()

bot = DiaBot()

ALLOWED_USER_ID = 1301944996261400656
banned_guilds = set()
allowed_roles_map = {}

# 指定されたチャンネルID
CHANNEL_REVIEW = 1510639675239432313
CHANNEL_LOG = 1524877240628805763

# ==========================================
# 🔐 評価・改善点入力フォーム (Modal)
# ==========================================
class ReviewModal(discord.ui.Modal, title="ボットの評価・改善点"):
    feedback = discord.ui.TextInput(
        label="問題点・改善点がありましたらご連絡ください",
        style=discord.TextStyle.long,
        placeholder="ここに入力してください（任意）",
        required=False
    )

    def __init__(self, stars: int, user_name: str):
        super().__init__()
        self.stars = stars
        self.user_name = user_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("💖 ご協力ありがとうございました！フィードバックを送信しました。", ephemeral=True)
        
        channel = bot.get_channel(CHANNEL_REVIEW)
        if channel:
            embed = discord.Embed(title="📊 新しいボット評価", color=discord.Color.gold())
            embed.add_field(name="ユーザー", value=self.user_name, inline=False)
            embed.add_field(name="評価", value="⭐" * self.stars, inline=False)
            embed.add_field(name="問題点・改善点", value=self.feedback.value or "（入力なし）", inline=False)
            await channel.send(embed=embed)

class ReviewButtons(discord.ui.View):
    def __init__(self, user_name: str):
        super().__init__(timeout=300)
        self.user_name = user_name

    async def handle_click(self, interaction: discord.Interaction, stars: int):
        await interaction.response.send_modal(ReviewModal(stars, self.user_name))

    @discord.ui.button(label="⭐1", style=discord.ButtonStyle.danger)
    async def star1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 1)
    @discord.ui.button(label="⭐2", style=discord.ButtonStyle.secondary)
    async def star2(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 2)
    @discord.ui.button(label="⭐3", style=discord.ButtonStyle.secondary)
    async def star3(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 3)
    @discord.ui.button(label="⭐4", style=discord.ButtonStyle.primary)
    async def star4(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 4)
    @discord.ui.button(label="⭐5", style=discord.ButtonStyle.success)
    async def star5(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 5)

# ==========================================
# 🔐 管理・権限コマンド
# ==========================================
@bot.tree.command(name="create-roles", description="どのロールが/createを使えるか設定します（サーバー管理者専用）")
@app_commands.describe(role_id="許可するロールのIDを入力してください")
async def create_roles(interaction: discord.Interaction, role_id: str):
    if not interaction.permissions.administrator:
        await interaction.response.send_message("❌ このコマンドはサーバーの管理者権限を持つ人のみ実行できます。", ephemeral=True)
        return
    try:
        r_id = int(role_id)
        allowed_roles_map[interaction.guild_id] = r_id
        await interaction.response.send_message(f"✅ 設定完了：ロールID `{r_id}` を持つメンバーのみ `/create` が使用可能です。")
    except ValueError:
        await interaction.response.send_message("❌ ロールIDは数字で入力してください。", ephemeral=True)

@bot.tree.command(name="shutdown", description="【管理者限定】このサーバーからBotを退出させます")
async def shutdown(interaction: discord.Interaction):
    if interaction.user.id != ALLOWED_USER_ID: return
    if interaction.guild:
        await interaction.response.send_message(f"👋 `{interaction.guild.name}` から退出します。")
        await interaction.guild.leave()

@bot.tree.command(name="subshutdown", description="【管理者限定】このサーバーでBotの機能を停止します")
async def subshutdown(interaction: discord.Interaction):
    if interaction.user.id != ALLOWED_USER_ID: return
    if interaction.guild:
        banned_guilds.add(interaction.guild.id)
        await interaction.response.send_message(f"🔒 このサーバー（`{interaction.guild.name}`）でのBotの利用を凍結しました。")

# --- クリエイター専用全サーバーログ表示コマンド ---
@bot.tree.command(name="serverlog", description="【クリエイター限定】Botが導入されている全サーバーと招待リンクの一覧を表示します")
async def serverlog(interaction: discord.Interaction):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    log_msg = "🏰 **導入サーバー一覧＆招待リンクログ**\n\n"
    for guild in bot.guilds:
        invite_link = "（招待作成の権限不足）"
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                try:
                    invite = await channel.create_invite(max_age=3600, max_uses=5)
                    invite_link = invite.url
                    break
                except Exception:
                    continue
        
        log_msg += f"■ **{guild.name}** (ID: `{guild.id}`)\n┗ 🔗 招待リンク: {invite_link}\n\n"
        
        if len(log_msg) > 1800:
            await interaction.followup.send(log_msg, ephemeral=True)
            log_msg = ""

    if log_msg:
        await interaction.followup.send(log_msg, ephemeral=True)

# ==========================================
# 🧠 ダイヤ計算＆画像生成エンジン
# ==========================================
def calculate_and_generate(data):
    stations, durations, types = data["stations"], data["durations"], data["types"]
    stops_raw, refuges, round_trips = data["stops"], data["refuges"], data["round_trips"]
    start_time_str, start_stations, want_diagram = data["start_time"], data["start_stations"], data["want_diagram"]

    stop_map = {}
    for t_idx, t_name in enumerate(types):
        raw_val = stops_raw[t_idx]
        stop_map[t_name] = "all" if raw_val == "各駅停車" else [s.strip() for s in raw_val.split("、")]

    start_station_map = {}
    for st_val in start_stations:
        if "＝" in st_val: k, v = st_val.split("＝", 1)
        elif "=" in st_val: k, v = st_val.split("=", 1)
        else: k, v = (types[0], st_val) if types else ("", st_val)
        start_station_map[k.strip()] = v.strip()

    base_time = datetime.datetime.strptime(start_time_str, "%H:%M")
    trains_schedule, global_id, current_pool_time = [], 1, base_time

    for ip in range(round_trips):
        for t_type in types:
            start_t = current_pool_time
            current_pool_time += datetime.timedelta(minutes=2)
            timetable, current_t = {}, start_t
            
            my_start_station = start_station_map.get(t_type, stations[0])
            start_idx = stations.index(my_start_station) if my_start_station in stations else 0

            for idx in range(start_idx, len(stations)):
                st = stations[idx]
                if idx == start_idx:
                    timetable[st] = {"arr": current_t.strftime("%H:%M:%S"), "dep": current_t.strftime("%H:%M:%S"), "note": "始発"}
                else:
                    sec_val = durations[idx-1] if (idx-1) < len(durations) else 120
                    current_t += datetime.timedelta(seconds=sec_val)
                    arr_time = current_t
                    is_stop = (stop_map.get(t_type) == "all") or (st in stop_map.get(t_type, [])) or (idx == len(stations)-1)
                    note = ""
                    
                    if stop_map.get(t_type) == "all" and st in refuges and idx != len(stations)-1:
                        current_t += datetime.timedelta(seconds=120)
                        note = "優等列車退避"
                        
                    if is_stop:
                        dep_time = current_t
                        note = "終着" if idx == len(stations)-1 else note
                        if idx != len(stations)-1: current_t += datetime.timedelta(seconds=30)
                        timetable[st] = {"arr": arr_time.strftime("%H:%M:%S"), "dep": dep_time.strftime("%H:%M:%S"), "note": note}
                    else:
                        timetable[st] = {"arr": arr_time.strftime("%H:%M:%S"), "dep": arr_time.strftime("%H:%M:%S"), "note": "通過"}
            
            trains_schedule.append({"id": f"{global_id}M", "type": t_type, "stops": timetable})
            global_id += 1

    output_text = f"## 🚂 生成されたカスタム運行ダイヤ\n\n"
    for ts in trains_schedule:
        output_text += f"**【{ts['type']} ({ts['id']})】**\n"
        output_text += "```\n種別\t\t到着時間\t発車時間\t備考\n"
        for st in stations:
            st_data = ts["stops"].get(st, {"arr": "--:--:--", "dep": "--:--:--", "note": ""})
            output_text += f"{st[:4].ljust(6)}\t{st_data['arr']}\t{st_data['dep']}\t{st_data['note']}\n"
        output_text += "```\n"

    img_byte_arr = None
    if want_diagram:
        img = Image.new("RGB", (600, 400), "white")
        draw = ImageDraw.Draw(img)
        y_step = 300 / max(1, len(stations)-1)
        for idx, st in enumerate(stations):
            y = 50 + idx * y_step
            draw.line([(50, y), (550, y)], fill="gray", width=1)
            draw.text((10, y-5), st[:2], fill="black")
            
        colors = {"各駅停車": "blue", "快速": "orange", "特急": "red"}
        for ts in trains_schedule:
            points = []
            for idx, st in enumerate(stations):
                st_data = ts["stops"].get(st)
                if st_data and st_data["arr"] != "--:--:--":
                    t_obj = datetime.datetime.strptime(st_data["arr"], "%H:%M:%S")
                    diff_min = (t_obj - base_time).total_seconds() / 60
                    points.append((50 + (diff_min * 8), 50 + idx * y_step))
            if len(points) > 1:
                draw.line(points, fill=colors.get(ts["type"], "black"), width=2)

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
    
    return output_text, img_byte_arr

# ==========================================
# 📱 DM 一問一答対話システム
# ==========================================
@bot.tree.command(name="create", description="新しく鉄道のダイヤを作成します")
async def create_dia(interaction: discord.Interaction):
    if interaction.guild and interaction.guild.id in banned_guilds:
        await interaction.response.send_message("❌ このサーバーでのBotの利用は凍結されています。", ephemeral=True)
        return

    required_role_id = allowed_roles_map.get(interaction.guild_id)
    if required_role_id and required_role_id not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ 使用する権限（指定されたロール）を持っていません。", ephemeral=True)
        return

    user, server_name = interaction.user, interaction.guild.name if interaction.guild else "DM"
    try:
        await user.send("🚂 **鉄道ダイヤ作成ウィザードへようこそ！**\nこれからの質問にそのままDMで回答してください。\n※制限時間は各**5分**です。")
        await interaction.response.send_message(f"📩 {user.mention} さん、DMを確認してください！", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ DMを送信できません。設定を確認してください。", ephemeral=True)
        return

    collected = {"stations": [], "durations": [], "types": [], "stops": [], "refuges": [], "round_trips": 1, "start_time": "10:00", "start_stations": [], "want_diagram": True}

    def check(m): return m.author == user and isinstance(m.channel, discord.DMChannel)

    async def ask(title, question, is_required=True):
        await user.send(f"### ■ タイトル：{title}\n{question}{' (必須)' if is_required else ' (任意・なければ「なし」)'}")
        try:
            msg = await bot.wait_for('message', check=check, timeout=300.0)
            return msg.content.strip()
        except asyncio.TimeoutError:
            await user.send("⏰ **タイムアウト:** 5分間回答がなかったためキャンセルされました。")
            return None

    # 1. 停車駅入力
    s_stop = False
    for i in range(1, 16):
        if s_stop: continue
        res = await ask("停車駅", f"{i}問目：停車駅{i}", is_required=(i<=3))
        if res is None: return
        if res == "なし" and i > 3: s_stop = True
        else: collected["stations"].append(res)

    # 2. 所要時間入力（秒数）
    st_count = len(collected["stations"])
    await user.send("⚠️ **これからの所要時間は、すべて「秒」で答えてください！**")
    for i in range(1, 15):
        if i >= st_count: continue
        res = await ask("所要時間", f"{i}問目：{collected['stations'][i-1]}〜{collected['stations'][i]}（秒数のみ）", is_required=(i<=2))
        if res is None: return
        collected["durations"].append(int(res))

    # 3. 種別入力
    t_stop = False
    for i in range(1, 6):
        if t_stop: continue
        res = await ask("種別", f"{i}問目：{'任意' if i>1 else ''}種別記入（例：{'各駅停車' if i==1 else '準急'}）", is_required=(i==1))
        if res is None: return
        if res == "なし" and i > 1: t_stop = True
        else: collected["types"].append(res)

    # 4. 各種別停車駅
    for i, t_name in enumerate(collected["types"]):
        res = await ask("各種別停車駅", f"{i+1}問目：【**{t_name}**】の停車駅：\n※各駅停車の場合は『各駅停車』と書けば全駅停車になります。例：東京、千葉、上総一ノ宮", is_required=(i==0))
        if res is None: return
        collected["stops"].append(res)

    # 5. 退避
    res = await ask("退避（書き方例：東京、品川、久里浜）", "退避可能駅：（無ければなし）", is_required=False)
    if res is None: return
    if res != "なし": collected["refuges"] = [r.strip() for r in res.split("、")]

    # 6. その他設定
    res = await ask("その他設定", "往復数：（数字のみ）", is_required=True)
    if res is None: return
    collected["round_trips"] = int(res)

    res = await ask("その他設定", "開始時間：（例：10:00）", is_required=True)
    if res is None: return
    collected["start_time"] = res

    for t_name in collected["types"]:
        res = await ask("その他設定", f"種別「**{t_name}**」の始発駅（3つまで）：", is_required=True)
        if res is None: return
        collected["start_stations"].append(f"{t_name}＝{res}")

    # 7. ダイヤグラム選択
    confirm_msg = await user.send("### ■ タイトル：その他設定\nダイヤグラムを出力しますか？\n✅（はい）か❌（いいえ）のリアクションで答えてください。")
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")

    try:
        rx, rx_u = await bot.wait_for('reaction_add', check=lambda r, u: u == user and str(r.emoji) in ["✅", "❌"] and r.message.id == confirm_msg.id, timeout=300.0)
        collected["want_diagram"] = (str(rx.emoji) == "✅")
    except asyncio.TimeoutError:
        collected["want_diagram"] = False

    # --- 計算と送信処理 ---
    await user.send("🔄 ダイヤを作成しています…")
    await asyncio.sleep(1)
    
    timetable_text, img_bin = calculate_and_generate(collected)
    
    # 1. ユーザーのDMへ送信
    files_dm = [discord.File(fp=io.BytesIO(img_bin.getvalue()), filename="diagram.png")] if img_bin else []
    await user.send(content=timetable_text, files=files_dm)
    
    # 2. 指定のログチャンネルへ転送
    log_channel = bot.get_channel(CHANNEL_LOG)
    if log_channel:
        log_text = f"📢 **【{server_name}】サーバーでダイヤが作成されました**\n\n{timetable_text}"
        files_log = [discord.File(fp=io.BytesIO(img_bin.getvalue()), filename="diagram.png")] if img_bin else []
        await log_channel.send(content=log_text, files=files_log)

    # 3. DMに評価アンケートを送信
    view = ReviewButtons(user.name)
    await user.send("⭐ **評価をお願いします**\nこのボットの使い心地はいかがでしたか？ボタンを選んでください。", view=view)

# 🌐 起動処理
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if TOKEN:
    keep_alive() # Webサーバーを別スレッドで立ち上げる
    bot.run(TOKEN)
else:
    print("❌ エラー: 環境変数 'DISCORD_BOT_TOKEN' がありません。")