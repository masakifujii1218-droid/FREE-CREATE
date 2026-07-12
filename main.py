import sys
import site
import os

# Renderが実際にインストールしたライブラリの隠し場所を自動取得して最優先で追加
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.insert(0, user_site)

import discord
from discord import app_commands
from discord.ext import commands, tasks
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
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ==========================================
# ⚙️ インテントの設定（ユーザー・サーバー参加検知を有効化）
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True
intents.members = True # メンバー情報の正確な取得に必要

class DiaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()

bot = DiaBot()

ALLOWED_USER_ID = 1301944996261400656
ADMIN_ROLE_ID = 1510021467167789104 
banned_guilds = set() # 利用凍結サーバーID
banned_users = set()  # 🚫 ブラックリストユーザーID
allowed_roles_map = {}

# 指定されたチャンネルID
CHANNEL_REVIEW = 1510639675239432313
CHANNEL_LOG = 1524877240628805763

# キャッシュ用サーバーログデータと起動時間記録
server_log_cache = ""
start_time_dt = None       # Botが起動した時刻
last_refresh_dt = None     # サーバーログが最後に更新された時刻

# ==========================================
# 🔄 1時間自動更新ループ（バックグラウンドタスク）
# ==========================================
@tasks.loop(hours=1.0)
async def refresh_server_log_loop():
    """導入サーバー一覧と招待リンクのデータを1時間ごとにバックグラウンドで安全に更新します"""
    global server_log_cache, last_refresh_dt
    await bot.wait_until_ready()
    
    try:
        log_msg = f"🏰 **導入サーバー一覧＆招待リンクログ (最終自動更新: {datetime.datetime.now().strftime('%m/%d %H:%M:%S')})**\n\n"
        
        for guild in bot.guilds:
            member_count = guild.member_count
            invite_link = "（招待作成の権限不足）"
            
            # 1時間おきなので、API制限にかからないよう安全に招待リンクを1つ作成
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).create_instant_invite:
                    try:
                        invite = await channel.create_invite(max_age=3600, max_uses=5)
                        invite_link = invite.url
                        break
                    except Exception:
                        continue
            
            log_msg += f"■ **{guild.name}** (ID: `{guild.id}`)\n┗ 🔗 招待リンク: {invite_link} | 👥 人数: {member_count}人\n\n"
        
        server_log_cache = log_msg
        last_refresh_dt = datetime.datetime.now() # 最終更新時間を記録
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Server logs and invites successfully updated (Hourly).")
    except Exception as e:
        print(f"⚠️ ログ更新エラー: {e}")

# ==========================================
# 📥 サーバー追加（参加）時の自動DM送信イベント
# ==========================================
@bot.event
async def on_guild_join(guild: discord.Guild):
    if guild.id in banned_guilds:
        await guild.leave()
        return

    owner = guild.owner
    if owner:
        try:
            embed = discord.Embed(
                title="🏰 ボットを追加してくれてありがとうございます！",
                description=f"この度は **{guild.name}** に当ボットを導入いただき、誠にありがとうございます！",
                color=discord.Color.green()
            )
            embed.add_field(
                name="🚀 すぐに使えます！",
                value="メンバーの方はサーバー内で `/create` コマンドを実行することで、DMを通していつでも自由にダイヤを作成可能です。",
                inline=False
            )
            embed.add_field(
                name="⚙️ `/create-roles` コマンドについて",
                value="初期状態では誰でも `/create` を使用できますが、管理者がこのコマンドを使うことで「**特定の役職（ロール）を持っているメンバーだけ**」に作成権限を絞り込むことができます。",
                inline=False
            )
            embed.set_footer(text="Free Create をお楽しみください！")
            await owner.send(embed=embed)
        except discord.Forbidden:
            print(f"⚠️ サーバー「{guild.name}」のオーナーにDMを送信できませんでした。")
        except Exception as e:
            print(f"⚠️ サーバー参加時DM送信エラー: {e}")

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
    if interaction.user.id in banned_users:
        await interaction.response.send_message("❌ あなたはBotの利用をブラックリストにより制限されています。", ephemeral=True)
        return
    if interaction.guild_id in banned_guilds:
        await interaction.response.send_message("❌ このサーバーでのBotの利用は凍結されています。", ephemeral=True)
        return
        
    is_admin = interaction.permissions.administrator if interaction.permissions else False
    is_owner = (interaction.user.id == ALLOWED_USER_ID)
    
    if not is_admin and not is_owner:
        await interaction.response.send_message("❌ このコマンドはサーバーの管理者権限を持つ人のみ実行できます。", ephemeral=True)
        return
    try:
        r_id = int(role_id)
        allowed_roles_map[interaction.guild_id] = r_id
        await interaction.response.send_message(f"✅ 設定完了：ロールID `{r_id}` を持つメンバーのみ `/create` が使用可能です。")
    except ValueError:
        await interaction.response.send_message("❌ ロールIDは数字で入力してください。", ephemeral=True)

@bot.tree.command(name="blacklist", description="【開発者限定】指定したサーバーをブラックリストに登録して即時退出させます")
@app_commands.describe(server_id="ブラックリストに登録するサーバーのID")
async def blacklist(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    try:
        g_id = int(server_id)
        banned_guilds.add(g_id)
        target_guild = bot.get_guild(g_id)
        left_msg = ""
        if target_guild:
            await target_guild.leave()
            left_msg = f"（該当サーバー「{target_guild.name}」から即時退出しました）"
        await interaction.response.send_message(f"🚫 サーバーID `{g_id}` をブラックリストに登録しました。{left_msg}", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ サーバーIDは数字で入力してください。", ephemeral=True)

@bot.tree.command(name="unblacklist", description="【開発者限定】指定したサーバーのブラックリスト登録を解除します")
@app_commands.describe(server_id="ブラックリストから解除するサーバーのID")
async def unblacklist(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    try:
        g_id = int(server_id)
        if g_id in banned_guilds:
            banned_guilds.remove(g_id)
            await interaction.response.send_message(f"🔓 サーバーID `{g_id}` のブラックリストを解除しました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ サーバーID `{g_id}` は登録されていません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ サーバーIDは数字で入力してください。", ephemeral=True)

@bot.tree.command(name="blacklists", description="【開発者限定】ブラックリストに登録されているサーバーの一覧を表示します")
async def blacklists(interaction: discord.Interaction):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    if not banned_guilds:
        await interaction.response.send_message("ℹ️ 現在ブラックリストに登録されているサーバーはありません。", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    msg = "🚫 **ブラックリスト登録サーバー一覧**\n\n"
    for g_id in banned_guilds:
        guild = bot.get_guild(g_id)
        guild_name = f"**{guild.name}**" if guild else "*(Bot退出済み/不明のサーバー)*"
        msg += f"・ ID: `{g_id}` ➔ {guild_name}\n"
        if len(msg) > 1800:
            await interaction.followup.send(msg, ephemeral=True)
            msg = ""
    if msg:
        await interaction.followup.send(msg, ephemeral=True)

@bot.tree.command(name="user-blacklist", description="【開発者限定】指定したユーザーをブラックリストに登録して一切の操作を拒否します")
@app_commands.describe(user_id="ブラックリストに登録するユーザーのID")
async def user_blacklist(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    try:
        u_id = int(user_id)
        banned_users.add(u_id)
        await interaction.response.send_message(f"🚫 ユーザーID `{u_id}` をブラックリストに登録しました。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ ユーザーIDは数字で入力してください。", ephemeral=True)

@bot.tree.command(name="user-unblacklist", description="【開発者限定】指定したユーザーのブラックリスト登録を解除します")
@app_commands.describe(user_id="ブラックリストから解除するユーザーのID")
async def user_unblacklist(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    try:
        u_id = int(user_id)
        if u_id in banned_users:
            banned_users.remove(u_id)
            await interaction.response.send_message(f"🔓 ユーザーID `{u_id}` のブラックリストを解除しました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ ユーザーID `{u_id}` は登録されていません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ ユーザーIDは数字で入力してください。", ephemeral=True)

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

@bot.tree.command(name="serverlog", description="【クリエイター限定】1時間ごとに自動更新される全導入サーバーと招待リンクの一覧を表示します")
async def serverlog(interaction: discord.Interaction):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    global server_log_cache
    
    if not server_log_cache:
        await interaction.followup.send("⏳ 現在ログを生成中です。起動から最大1時間かかるか、数分お待ちください。", ephemeral=True)
        return
        
    msg = server_log_cache
    while len(msg) > 1800:
        split_idx = msg.rfind("\n\n", 0, 1800)
        if split_idx == -1: split_idx = 1800
        await interaction.followup.send(msg[:split_idx], ephemeral=True)
        msg = msg[split_idx:]
        
    if msg:
        await interaction.followup.send(msg, ephemeral=True)

# ==========================================
# 📊 稼働状況ステータスコマンド (👑実行はあなた専用 / 表示は全員に見える)
# ==========================================
@bot.tree.command(name="botinfo", description="【作成者限定】ダイヤ作成所 | Free Create の現在の稼働状況をチェックします")
async def botinfo(interaction: discord.Interaction):
    # 👑 実行できるのはあなた（作成者）だけに制限するガード
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドはBotの作成者（開発者）専用のため、実行できません。", ephemeral=True)
        return

    # 1. 基本ステータス算出
    ping = round(bot.latency * 1000)
    guilds_count = f"{len(bot.guilds):,}"
    
    # 2. 全ユーザーの総数を集計
    total_users = sum(guild.member_count for guild in bot.guilds)
    users_count = f"{total_users:,}"
    
    # 3. Discord動的タイムスタンプの作成（何分前・何秒前を自動計算する特殊タグ）
    start_ts_r = f"<t:{int(start_time_dt.timestamp())}:R>" if start_time_dt else "⏳ 計測中"
    start_ts_f = f"<t:{int(start_time_dt.timestamp())}:F>" if start_time_dt else "⏳ 計測中"
    
    refresh_ts_r = f"<t:{int(last_refresh_dt.timestamp())}:R>" if last_refresh_dt else "⏳ まもなく初回更新"

    # 4. 埋め込み (Embed) パネルの構築
    embed = discord.Embed(
        title="📊 ダイヤ作成所 | Free Create 稼働状況",
        description="現在のステータス: 🟢 **正常稼働中**",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(
        name="🆔 BOT ID",
        value=f"`{bot.user.id}`",
        inline=False
    )
    embed.add_field(
        name="📶 Ping",
        value=f"**{ping} ms**",
        inline=False
    )
    embed.add_field(
        name="🏰 導入サーバー",
        value=f"**{guilds_count}** サーバー",
        inline=False
    )
    embed.add_field(
        name="👥 ユーザー総数",
        value=f"**{users_count}** 人",
        inline=False
    )
    embed.add_field(
        name="⏱️ 起動時間",
        value=f"**{start_ts_r}**\n({start_ts_f})",
        inline=False
    )
    embed.add_field(
        name="🔄 最終更新（サーバーログキャッシュ）",
        value=f"**{refresh_ts_r}**",
        inline=False
    )
    
    embed.set_footer(text=f"{bot.user.name}", icon_url=bot.user.display_avatar.url)

    # 💡 ephemeral=True を外すことで、出力されたパネルを「みんなが見える」ようにしました！
    await interaction.response.send_message(embed=embed)

# ==========================================
# 🧠 ダイヤ計算＆画像生成エンジン
# ==========================================
def calculate_and_generate(data):
    stations, durations, types = data["stations"], data["durations"], data["types"]
    stops_raw, refuges, round_trips = data["stops"], data["refuges"], data["round_trips"]
    num_trains = data.get("num_trains", 1)  
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
            set_id = ((global_id - 1) % num_trains) + 1
            
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
            
            trains_schedule.append({"id": f"{global_id}M", "set_id": f"第{set_id}編成", "type": t_type, "stops": timetable})
            global_id += 1

    output_text = f"## 🚂 生成されたカスタム運行ダイヤ\n\n"
    for ts in trains_schedule:
        output_text += f"**【{ts['type']} ({ts['id']}) ➔ {ts['set_id']}担当】**\n"
        output_text += "```\n"
        output_text += "駅名      | 到着時間   | 発車時間   | 備考\n"
        output_text += "--------------------------------------------------\n"
        for st in stations:
            st_data = ts["stops"].get(st, {"arr": "--:--:--", "dep": "--:--:--", "note": ""})
            
            st_name = st[:4].ljust(6)
            arr_t = st_data['arr'].ljust(8)
            dep_t = st_data['dep'].ljust(8)
            note = st_data['note']
            
            output_text += f"{st_name} | {arr_t} | {dep_t} | {note}\n"
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
    if interaction.user.id in banned_users:
        await interaction.response.send_message("❌ あなたはBotの利用をブラックリストにより制限されています。", ephemeral=True)
        return
    if interaction.guild and interaction.guild.id in banned_guilds:
        await interaction.response.send_message("❌ このサーバーでのBotの利用は凍結されています。", ephemeral=True)
        return

    required_role_id = allowed_roles_map.get(interaction.guild_id)
    user_permissions = interaction.user.guild_permissions if interaction.guild else None
    
    is_admin = user_permissions.administrator if user_permissions else False
    is_owner = (interaction.user.id == ALLOWED_USER_ID)
    has_admin_role = any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles) if interaction.guild else False

    if required_role_id and not is_admin and not is_owner and not has_admin_role:
        if required_role_id not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("❌ 使用する権限（指定されたロール）を持っていません。", ephemeral=True)
            return

    user, server_name = interaction.user, interaction.guild.name if interaction.guild else "DM"
    try:
        welcome_embed = discord.Embed(
            title="🚂 鉄道ダイヤ作成ウィザードへようこそ！",
            description="これからの質問にそのままDMで回答してください。\n※制限時間は各質問**5分**です。",
            color=discord.Color.blue()
        )
        welcome_embed.set_footer(text="いつでも「cancel」で中断、「back」で1つ前の質問に戻れます。")
        await user.send(embed=welcome_embed)
        await interaction.response.send_message(f"📩 {user.mention} さん、DMを確認してください！", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ DMを送信できません。設定を確認してください。", ephemeral=True)
        return

    collected = {
        "stations": [],
        "durations": [],
        "types": [],
        "stops": [],
        "refuges": [],
        "round_trips": 1,
        "num_trains": 1, 
        "start_time": "10:00",
        "start_stations": [],
        "want_diagram": True
    }

    def check(m): return m.author == user and isinstance(m.channel, discord.DMChannel)

    async def ask(title, question, is_required=True):
        embed = discord.Embed(title=f"■ {title}", description=question, color=discord.Color.green())
        if not is_required:
            embed.set_footer(text="（任意・なければ「なし」と入力）")
        content_notice = "-# 戻る場合は back 、キャンセルする場合は cancel"
        await user.send(embed=embed, content=content_notice)
        try:
            msg = await bot.wait_for('message', check=check, timeout=300.0)
            text = msg.content.strip()
            if text.lower() == "cancel": return "SIGNAL_CANCEL"
            if text.lower() == "back": return "SIGNAL_BACK"
            return text
        except asyncio.TimeoutError:
            return "SIGNAL_TIMEOUT"

    current_state = 0
    sub_idx = 0

    while current_state < 10: 
        if current_state == 0:
            if sub_idx < 0: 
                await user.send("💡 これ以上は戻れません。")
                sub_idx = 0
            is_req = (sub_idx <= 2)
            res = await ask("停車駅入力", f"{sub_idx + 1}問目：停車駅{sub_idx + 1}", is_required=is_req)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["stations"]) > sub_idx: collected["stations"].pop()
                continue
            if res == "なし" and not is_req:
                if len(collected["stations"]) < 3:
                    await user.send("❌ 駅は最低3つ以上入力してください。")
                    continue
                current_state = 1
                sub_idx = 0
            else:
                if sub_idx < len(collected["stations"]): collected["stations"][sub_idx] = res
                else: collected["stations"].append(res)
                sub_idx += 1
                if sub_idx >= 15:
                    current_state = 1
                    sub_idx = 0

        elif current_state == 1:
            st_count = len(collected["stations"])
            if sub_idx < 0:
                current_state = 0
                sub_idx = st_count - 1
                continue
            if sub_idx >= st_count - 1:
                current_state = 2
                sub_idx = 0
                continue
            if sub_idx == 0:
                await user.send("⚠️ **これからの所要時間は、すべて「秒」で答えてください！**")
            is_req = (sub_idx <= 1)
            st_from = collected["stations"][sub_idx]
            st_to = collected["stations"][sub_idx + 1]
            res = await ask("所要時間入力", f"{sub_idx + 1}問目：【{st_from}】〜【{st_to}】の所要時間（秒数のみ）", is_required=is_req)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["durations"]) > sub_idx: collected["durations"].pop()
                continue
            try:
                sec_val = int(res)
                if sub_idx < len(collected["durations"]): collected["durations"][sub_idx] = sec_val
                else: collected["durations"].append(sec_val)
                sub_idx += 1
            except ValueError:
                await user.send("❌ 数字（秒数）だけで入力してください。")

        elif current_state == 2:
            if sub_idx < 0:
                current_state = 1
                sub_idx = len(collected["stations"]) - 2
                continue
            is_req = (sub_idx == 0)
            res = await ask("種別入力", f"{sub_idx + 1}問目：{'任意' if not is_req else ''}種別記入（例：{'各駅停車' if is_req else '準急'}）", is_required=is_req)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["types"]) > sub_idx: collected["types"].pop()
                continue
            if res == "なし" and not is_req:
                if len(collected["types"]) < 1:
                    await user.send("❌ 種別は最低1つ以上入力してください。")
                    continue
                current_state = 3
                sub_idx = 0
            else:
                if sub_idx < len(collected["types"]): collected["types"][sub_idx] = res
                else: collected["types"].append(res)
                sub_idx += 1
                if sub_idx >= 5:
                    current_state = 3
                    sub_idx = 0

        elif current_state == 3:
            type_count = len(collected["types"])
            if sub_idx < 0:
                current_state = 2
                sub_idx = type_count - 1
                continue
            if sub_idx >= type_count:
                current_state = 4
                sub_idx = 0
                continue
            t_name = collected["types"][sub_idx]
            res = await ask("各種別停車駅", f"【**{t_name}**】の停車駅を入力してください。\n※各駅停車の場合は『各駅停車』と書けば全駅停車になります。\n例：東京、千葉、上総一ノ宮", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["stops"]) > sub_idx: collected["stops"].pop()
                continue
            if sub_idx < len(collected["stops"]): collected["stops"][sub_idx] = res
            else: collected["stops"].append(res)
            sub_idx += 1

        elif current_state == 4:
            res = await ask("退避駅設定", "退避可能駅を教えてください（書き方例：東京、品川、久里浜）", is_required=False)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 3
                sub_idx = len(collected["types"]) - 1
                continue
            if res != "なし": collected["refuges"] = [r.strip() for r in res.split("、")]
            else: collected["refuges"] = []
            current_state = 5
            sub_idx = 0

        elif current_state == 5:
            res = await ask("その他設定", "往復数を入力してください（数字のみ）", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 4
                continue
            try:
                collected["round_trips"] = int(res)
                current_state = 6 
            except ValueError:
                await user.send("❌ 数字だけで入力してください。")

        elif current_state == 6: 
            res = await ask("その他設定", "この路線全体の「総編成数（運用する車両の本数）」を入力してください（数字のみ）", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 5
                continue
            try:
                collected["num_trains"] = int(res)
                current_state = 7
            except ValueError:
                await user.send("❌ 数字だけで入力してください。")

        elif current_state == 7:
            res = await ask("その他設定", "開始時間を入力してください（例：10:00）", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 6
                continue
            collected["start_time"] = res
            current_state = 8
            sub_idx = 0

        elif current_state == 8:
            type_count = len(collected["types"])
            if sub_idx < 0:
                current_state = 7
                continue
            if sub_idx >= type_count:
                current_state = 9
                continue
            t_name = collected["types"][sub_idx]
            res = await ask("その他設定", f"種別「**{t_name}**」の始発駅を入力してください：", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["start_stations"]) > sub_idx: collected["start_stations"].pop()
                continue
            entry = f"{t_name}＝{res}"
            if sub_idx < len(collected["start_stations"]): collected["start_stations"][sub_idx] = entry
            else: collected["start_stations"].append(entry)
            sub_idx += 1

        elif current_state == 9:
            res = await ask("その他設定", "ダイヤグラムを出力しますか？（はい / いいえ でお答えください）", is_required=True)
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 8
                sub_idx = len(collected["types"]) - 1
                continue
            if res in ["はい", "はい ", "ハイ"]:
                collected["want_diagram"] = True
                current_state = 10
            elif res in ["いいえ", "いいえ ", "イイエ"]:
                collected["want_diagram"] = False
                current_state = 10
            else:
                await user.send("❌ **入力エラー:** 「はい」または「いいえ」の文字だけで入力してください。")

    if current_state != 10:
        cancel_embed = discord.Embed(title="🔒 キャンセル完了", description="ダイヤ作成ウィザードを中断しました。またいつでも `/create` を実行してください！", color=discord.Color.red())
        await user.send(embed=cancel_embed)
        return

    await user.send("🔄 ダイヤを作成しています…")
    await asyncio.sleep(1)
    
    timetable_text, img_bin = calculate_and_generate(collected)
    
    files_dm = [discord.File(fp=io.BytesIO(img_bin.getvalue()), filename="diagram.png")] if img_bin else []
    await user.send(content=timetable_text, files=files_dm)
    
    log_channel = bot.get_channel(CHANNEL_LOG)
    if log_channel:
        log_text = f"📢 **【{server_name}】サーバーでダイヤが作成されました**\n\n{timetable_text}"
        files_log = [discord.File(fp=io.BytesIO(img_bin.getvalue()), filename="diagram.png")] if img_bin else []
        await log_channel.send(content=log_text, files=files_log)

    view = ReviewButtons(user.name)
    await user.send("⭐ **評価をお願いします**\nこのボットの使い心地はいかがでしたか？ボタンを選んでください。", view=view)

# ==========================================
# ⚙️ 起動処理
# ==========================================
@bot.event
async def on_ready():
    global start_time_dt
    start_time_dt = datetime.datetime.now() # 起動時刻をシステムに記録
    
    if not refresh_server_log_loop.is_running():
        refresh_server_log_loop.start()
    print(f"{bot.user} で正常にログインしました")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if TOKEN:
    keep_alive()
    bot.run(TOKEN)
else:
    print("❌ エラー: 環境変数 'DISCORD_BOT_TOKEN' がありません。")
    # 💡 スマホ用に、一番下にエラー原因を表示するシステム
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    # すでにBotが「考えてる最中（defer）」ならそれを使う、そうじゃなければ新規で返信する
    if interaction.response.is_done():
        send_func = interaction.followup.send
    else:
        send_func = interaction.response.send_message

    # スマホで見やすいメッセージを作成（一番下にエラー内容を配置）
    error_msg = (
        "⚠️ **Botがクラッシュしました**\n"
        "データ量が多すぎるか、設定された数字に矛盾がある可能性があります。\n\n"
        f"🧐 **原因（エラー内容）： `{error}`**"
    )
    
    # チャンネルに送信
    await send_func(error_msg, ephemeral=False)