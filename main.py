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
intents.members = True # オーナーへのDM送信やメンバー情報の正確な取得に必要

class DiaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()

bot = DiaBot()

ALLOWED_USER_ID = 1301944996261400656
banned_guilds = set() # ブラックリストのサーバーIDがここに格納されます
allowed_roles_map = {}

# 指定されたチャンネルID
CHANNEL_REVIEW = 1510639675239432313
CHANNEL_LOG = 1524877240628805763

# ==========================================
# 📥 サーバー追加（参加）時の自動DM送信イベント
# ==========================================
@bot.event
async def on_guild_join(guild: discord.Guild):
    # 利用凍結（ブラックリスト）されているサーバーなら即退出
    if guild.id in banned_guilds:
        await guild.leave()
        return

    # サーバーのオーナーを取得
    owner = guild.owner
    if owner:
        try:
            # 箱（Embed）を作成
            embed = discord.Embed(
                title="🏰 ボットを追加してくれてありがとうございます！",
                description=f"この度は **{guild.name}** に当ボットを導入いただき、誠にありがとうございます！",
                color=discord.Color.red()
            )
            
            # 最重要：サポートサーバーでの申告必須アナウンス
            embed.add_field(
                name="⚠️ 【最重要】サポートサーバーでの追加報告（申告）のお願い",
                value="当ボットの有効化手続きのため、**サポートサーバー内での『BOT追加報告（申告）』が必須**となっております。\n\n"
                      "**※期日までに申告が行われない場合、こちらのサーバーでボットの機能が自動的にロック（利用凍結）され、一切使用できなくなります。** 必ずお早めにご報告をお願いいたします。",
                inline=False
            )
            
            embed.add_field(
                name="📢 サポートサーバー・申請先はこちら",
                value="下記リンクよりサポートサーバーへご参加いただき、指定 of 報告チャンネルにてサーバー名等をご申告ください。\n\n"
                      "**🔗 サポートサーバー：**\nhttps://discord.gg/vDcFTK2wbh",
                inline=False
            )

            embed.add_field(
                name="⚙️ `/create-roles` コマンドについて",
                value="初期状態では誰でも `/create` コマンドを使用できますが、このコマンドを使うことで「**特定の役職（ロール）を持っているメンバーだけ**」にダイヤ作成権限を絞り込むことができます。\n"
                      "*(※サーバーの管理者権限を持つユーザーのみ実行可能です)*",
                inline=False
            )
            
            embed.set_footer(text="お手数をおかけしますが、ボット運用の維持・安全対策のためご協力をお願いいたします。")
            
            # オーナーのDMへ送信
            await owner.send(embed=embed)
        except discord.Forbidden:
            print(f"⚠️ サーバー「{guild.name}」のオーナー({owner.name})にDMを送信できませんでした（DM拒否設定など）。")
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
    if not interaction.permissions.administrator:
        await interaction.response.send_message("❌ このコマンドはサーバーの管理者権限を持つ人のみ実行できます。", ephemeral=True)
        return
    try:
        r_id = int(role_id)
        allowed_roles_map[interaction.guild_id] = r_id
        await interaction.response.send_message(f"✅ 設定完了：ロールID `{r_id}` を持つメンバーのみ `/create` が使用可能です。")
    except ValueError:
        await interaction.response.send_message("❌ ロールIDは数字で入力してください。", ephemeral=True)

# 🚫 新設：ブラックリスト登録コマンド（開発者限定）
@bot.tree.command(name="blacklist", description="【開発者限定】指定したサーバーをブラックリストに登録して即時退出させます")
@app_commands.describe(server_id="ブラックリストに登録するサーバーのID")
async def blacklist(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != ALLOWED_USER_ID:
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return
    
    try:
        g_id = int(server_id)
        banned_guilds.add(g_id)
        
        # もしBotが現在そのサーバーに導入されているなら強制退出させる
        target_guild = bot.get_guild(g_id)
        left_msg = ""
        if target_guild:
            await target_guild.leave()
            left_msg = f"（該当サーバー「{target_guild.name}」から即時退出しました）"
            
        await interaction.response.send_message(f"🚫 サーバーID `{g_id}` をブラックリストに登録しました。{left_msg}", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ サーバーIDは数字（18桁〜の文字列）で入力してください。", ephemeral=True)

# 🔓 新設：ブラックリスト解除コマンド（開発者限定）
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
            await interaction.response.send_message(f"🔓 サーバーID `{g_id}` のブラックリストを解除しました。再導入が可能です。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ サーバーID `{g_id}` はブラックリストに登録されていません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ サーバーIDは数字で入力してください。", ephemeral=True)

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
# 📱 DM 一問一答対話システム（FSM改良版）
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
        "start_time": "10:00",
        "start_stations": [],
        "want_diagram": True
    }

    def check(m): return m.author == user and isinstance(m.channel, discord.DMChannel)

    async def ask(title, question, is_required=True):
        embed = discord.Embed(title=f"■ {title}", description=question, color=discord.Color.green())
        if not is_required:
            embed.set_footer(text="（任意・なければ「なし」と入力）")
        
        content_notice = "-# 戻る場合は back 、キャンセルする場合のは cancel"
        await user.send(embed=embed, content=content_notice)
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=300.0)
            text = msg.content.strip()
            
            if text.lower() == "cancel":
                return "SIGNAL_CANCEL"
            if text.lower() == "back":
                return "SIGNAL_BACK"
                
            return text
        except asyncio.TimeoutError:
            return "SIGNAL_TIMEOUT"

    current_state = 0
    sub_idx = 0

    while current_state < 9:
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
                if sub_idx >= 0 and len(collected["stations"]) > sub_idx:
                    collected["stations"].pop()
                continue
                
            if res == "なし" and not is_req:
                if len(collected["stations"]) < 3:
                    await user.send("❌ 駅は最低3つ以上入力してください。")
                    continue
                current_state = 1
                sub_idx = 0
            else:
                if sub_idx < len(collected["stations"]):
                    collected["stations"][sub_idx] = res
                else:
                    collected["stations"].append(res)
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
                if sub_idx >= 0 and len(collected["durations"]) > sub_idx:
                    collected["durations"].pop()
                continue
                
            try:
                sec_val = int(res)
                if sub_idx < len(collected["durations"]):
                    collected["durations"][sub_idx] = sec_val
                else:
                    collected["durations"].append(sec_val)
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
                if sub_idx >= 0 and len(collected["types"]) > sub_idx:
                    collected["types"].pop()
                continue
                
            if res == "なし" and not is_req:
                if len(collected["types"]) < 1:
                    await user.send("❌ 種別は最低1つ以上入力してください。")
                    continue
                current_state = 3
                sub_idx = 0
            else:
                if sub_idx < len(collected["types"]):
                    collected["types"][sub_idx] = res
                else:
                    collected["types"].append(res)
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
                if sub_idx >= 0 and len(collected["stops"]) > sub_idx:
                    collected["stops"].pop()
                continue
                
            if sub_idx < len(collected["stops"]):
                collected["stops"][sub_idx] = res
            else:
                collected["stops"].append(res)
            sub_idx += 1

        elif current_state == 4:
            res = await ask("退避駅設定", "退避可能駅を教えてください（書き方例：東京、品川、久里浜）", is_required=False)
            
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 3
                sub_idx = len(collected["types"]) - 1
                continue
                
            if res != "なし":
                collected["refuges"] = [r.strip() for r in res.split("、")]
            else:
                collected["refuges"] = []
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
            res = await ask("その他設定", "開始時間を入力してください（例：10:00）", is_required=True)
            
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 5
                continue
                
            collected["start_time"] = res
            current_state = 7
            sub_idx = 0

        elif current_state == 7:
            type_count = len(collected["types"])
            if sub_idx < 0:
                current_state = 6
                continue
                
            if sub_idx >= type_count:
                current_state = 8
                continue
                
            t_name = collected["types"][sub_idx]
            res = await ask("その他設定", f"種別「**{t_name}**」の始発駅を入力してください：", is_required=True)
            
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                sub_idx -= 1
                if sub_idx >= 0 and len(collected["start_stations"]) > sub_idx:
                    collected["start_stations"].pop()
                continue
                
            entry = f"{t_name}＝{res}"
            if sub_idx < len(collected["start_stations"]):
                collected["start_stations"][sub_idx] = entry
            else:
                collected["start_stations"].append(entry)
            sub_idx += 1

        elif current_state == 8:
            res = await ask("その他設定", "ダイヤグラムを出力しますか？（はい / いいえ でお答えください）", is_required=True)
            
            if res == "SIGNAL_CANCEL": break
            elif res == "SIGNAL_TIMEOUT": return
            elif res == "SIGNAL_BACK":
                current_state = 7
                sub_idx = len(collected["types"]) - 1
                continue
                
            if res in ["はい", "はい ", "ハイ"]:
                collected["want_diagram"] = True
                current_state = 9
            elif res in ["いいえ", "いいえ ", "イイエ"]:
                collected["want_diagram"] = False
                current_state = 9
            else:
                await user.send("❌ **入力エラー:** 「はい」または「いいえ」の文字だけで入力してください。")

    if current_state != 9:
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

# 🌐 起動処理
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if TOKEN:
    keep_alive()
    bot.run(TOKEN)
else:
    print("❌ エラー: 環境変数 'DISCORD_BOT_TOKEN' がありません。")