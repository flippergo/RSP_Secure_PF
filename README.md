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
python -m py_compile rsp_group_engine.py test_rsp_group_engine.py
```

## 注意

`num_match=10000` では、別プロセス分離と通信のため実行に時間がかかります。動作確認中は `num_match=10` や `num_match=100` に下げ、本番実行時だけ `10000` に戻すと確認しやすくなります。
