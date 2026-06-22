# Secure RSP Group Tournament PF

`rsp_vs_group.ipynb` は、`group_agents/` 内の各 `rsp_group_<n>.py` を団体戦で対戦させるためのNotebookです。実際の対戦処理は `rsp_group_engine.py` に切り出してあります。

## ファイル構成

- `rsp_vs_group.ipynb`: 授業・確認用の実行Notebook
- `rsp_group_engine.py`: 堅牢化した団体戦エンジン
- `test_rsp_group_engine.py`: エンジンの検証用テスト
- `rule.pdf`: 提出ルールと対戦ルール
- `group_agents/`: 提出ファイル `rsp_group_<n>.py` を置くディレクトリ

## 提出ファイルの置き方

`group_agents/` に、次の形式のファイルを置きます。

```text
group_agents/
  rsp_group_1.py
  rsp_group_2.py
  rsp_group_14.py
```

ファイル名は `rsp_group_<グループ番号>.py` のみ認識されます。`__pycache__` や別名のファイルは無視されます。

各提出ファイルには、`RSP_Agent_1`, `RSP_Agent_2`, `RSP_Agent_3` を定義してください。各クラスは `__init__(num_match=...)`, `output_hand()`, `get_hand(oppo_hand)` を持つ必要があります。

## Notebookで実行する

1. `rsp_vs_group.ipynb` を開きます。
2. 先頭セルから順に実行します。
3. 必要に応じて、最初のコードセルで設定値を変更します。

```python
base_dir = Path("group_agents")
num_match = 10000
team_size = 3
timeout_seconds = 1.0
```

主な出力は次の通りです。

- `group_scores`: グループごとの合計スコア
- `scores`: エージェントごとの対戦スコア表
- `details`: 各対戦の詳細ログ

Excel出力用セルは最後にあります。必要な場合だけコメントアウトを外して実行してください。

## Pythonから実行する

コマンドラインで実行する場合:

```powershell
python rsp_group_engine.py
```

Pythonコードから使う場合:

```python
from rsp_group_engine import run_group_tournament_from_dir

result = run_group_tournament_from_dir(
    "group_agents",
    num_match=10000,
    team_size=3,
    timeout_seconds=1.0,
)

print(result["group_scores"])
print(result["scores"])
print(result["details"])
print(result["validation_errors"])
```

## MCPサーバとして使う

`rsp_mcp_server.py` はstdioで通信するローカルMCPサーバです。MCPクライアント側では、次のようにこのファイルをPythonで起動する設定にしてください。

```json
{
  "mcpServers": {
    "rsp-secure-pf": {
      "command": "python",
      "args": [
        "C:/Users/hoppe/work/AISisDev/Secure_PF/rsp_mcp_server.py"
      ],
      "cwd": "C:/Users/hoppe/work/AISisDev/Secure_PF"
    }
  }
}
```

公開されるMCPツールは次の3つです。

- `list_rsp_group_agents`: `group_agents/` 内の `rsp_group_<n>.py` を列挙し、各提出ファイルの検証結果を返します。
- `validate_rsp_group_agents`: 対戦前の静的検査だけを実行し、全体として有効かどうかを返します。
- `run_rsp_group_tournament_from_dir`: セキュアPFで団体戦を実行し、グループ順位、全エージェント順位、スコア表、詳細ログ、Markdown表を返します。

`run_rsp_group_tournament_from_dir` の主な入力は次の通りです。

```json
{
  "group_agents_dir": "group_agents",
  "num_match": 10000,
  "team_size": 3,
  "timeout_seconds": 1.0,
  "include_score_matrix": true,
  "include_details": true
}
```

MCPの出力には、クライアント上で見やすいMarkdown表と、後処理しやすいJSONの両方を含めています。順位を手早く見たい場合はMarkdownの `Group Ranking`, `Group Score Chart`, `All Agent Ranking` を確認してください。

JSON出力の主な順位フィールドは次の通りです。

- `group_ranking`: グループごとの合計スコア順位
- `agent_ranking`: 参加した全エージェントのスコア順順位表。1グループ3体分すべてを対象に、`rank`, `agent`, `group`, `total` を返します。
- `member_ranking`: 既存互換用のフィールドです。内容は `agent_ranking` と同じです。

## 堅牢化の内容

`rsp_group_engine.py` は、提出コードをそのまま同一プロセスでimportしません。

- 対戦前にAST検査を行い、許可されたimportだけを通します。
- 許可importは `numpy`, `math`, `random`, `time`, `timeout_decorator` です。
- `sys`, `os`, `inspect`, `importlib`, `subprocess` など、PFや相手の状態を読めるモジュールは禁止です。
- `eval`, `exec`, `open`, `globals`, `locals`, `getattr`, `setattr`, `__import__` などは禁止です。
- `RSP_Agent_1..3` は別プロセスで実行され、PF本体や相手エージェントとメモリを共有しません。
- 各ラウンドでは両者の `output_hand()` を先に取得してから、勝敗判定後に `get_hand()` で相手の手を通知します。
- 各グループ対戦ごとにエージェントを新規生成するため、別の相手との対戦状態は持ち越されません。

完全なOSレベルのサンドボックスではありませんが、公開Notebookの実装詳細を利用した先読みや呼び出し元フレーム参照は防ぐ設計です。

### 旧Notebookから塞いだ主な穴

旧 `rsp_vs_group.ipynb` では、提出ファイルをPF本体と同じPythonプロセスに読み込み、そのまま呼び出していました。現行版では、次の点を重点的に塞いでいます。

| 旧Notebookの処理 | 問題点 | 現行版での対策 |
|---|---|---|
| `importlib.import_module(base_dir+"."+groups[i])` で提出ファイルを通常import | 提出コードがPF本体と同じプロセス内で動くため、`sys.modules` や `inspect` などからPFや相手モジュールの状態に触れる余地がある | 提出コードを別プロセスのワーカーで実行し、PF本体とはJSONメッセージだけで通信する |
| `exec(f"agent1[{j}]=group1.RSP_Agent_{j+1}(...)")` でエージェントを生成 | 文字列実行により、名前解決や例外原因が見えにくく、PF側の実装詳細に依存しやすい | PF側では明示的にクラスを取得し、提出コード側では `exec`, `eval`, `getattr`, `setattr` などをAST検査で禁止する |
| `agent1.output_hand()` の後に `agent2.output_hand()` を呼ぶ | 後手側が呼び出し元フレームを覗けると、先手の手を読める可能性がある | 両者へ先に `output_hand` 要求を送り、両方の応答が揃ってから勝敗判定する |
| 外側ループで生成した `agent1` を複数の相手戦で再利用 | 先に戦った相手の履歴が次の相手との対戦に持ち越され、対戦順序によるバイアスが出る | 各グループ対戦ごとに両チームのエージェントを新規生成する |
| `get_hand` を2体まとめて `try: ... except: pass` で処理 | どちらのエージェントが失敗したか分からず、失敗理由も記録されない | 各エージェントの `status`, `reason`, `timeouts`, `invalid_moves` などを詳細ログに残す |
| 提出コードのimportや組み込み関数利用を事前検査しない | `sys`, `os`, `inspect`, `importlib`, `globals`, `locals`, `__import__` などでPF内部や環境へ触れる抜け道がある | AST検査で許可importを `numpy`, `math`, `random`, `time`, `timeout_decorator` に限定し、危険なimport・関数・dunderアクセスを禁止する |
| タイムアウトを提出側の `timeout_decorator` に依存 | デコレータの削除・無効化・想定外の停止にPF側だけでは対応しにくい | ルール検査でデコレータを確認しつつ、PF側でも `__init__`, `output_hand`, `get_hand` にタイムアウトをかける |

## バグ・異常時の扱い

- `__init__`, `output_hand`, `get_hand` の例外やタイムアウトは、そのエージェントのバグとして扱います。
- バグがあるエージェントのその対戦スコアは `0` です。
- 相手だけが正常な場合、正常側のスコアは `1.0` になります。
- 手は `0`, `1`, `2` の整数だけ有効です。
- `bool`, 文字列、小数、範囲外値は無効手として扱います。

## テスト

エンジンの検証テストは次で実行できます。

```powershell
python -m unittest -v test_rsp_group_engine.py
```

構文確認だけ行う場合:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m py_compile rsp_group_engine.py rsp_mcp_server.py test_rsp_group_engine.py
```

## 注意

`num_match=10000` では、別プロセス分離と通信のため実行に時間がかかります。動作確認中は `num_match=10` や `num_match=100` に下げ、本番実行時だけ `10000` に戻すと確認しやすくなります。
