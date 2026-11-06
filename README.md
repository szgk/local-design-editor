# Local Design Editor

既存デザインの指定部分だけを編集する、ローカル実行のCLIです。**指定外の画素を原画像からコピーし、RGBとAlphaの差分ゼロを検証します。** CodexなどのコーディングエージェントからJSONで操作できます。

![Generic robot sample](examples/robot.png)

## Phase 1

| 操作 | 実装 |
| --- | --- |
| Extract | 原画素の矩形切り抜きと任意の透過マスク。隠れた部分は補完しない |
| Recolor | OpenCVの色相変更。彩度・明度とAlphaを保持する設計。RGB変換の丸めは生じる |
| Mask | 矩形・多角形、編集可能・保護・参照マスク、内側フェザー |
| Inpaint / Redesign | ローカルComfyUIのSD1.5 Inpaintingワークフロー |
| Composite | 候補画像を許可領域内だけ原画像へ合成 |
| Verify | 保護領域のRGBA完全一致、解像度、変更画素数、差分画像 |
| History | 実行ごとの不変な原画像コピー、SHA256、設定、結果、失敗理由 |

マスク内の品質や指示の達成は自動保証しません。`pixel_preservation_pass`と`intent_review`を分け、画素保持に合格しても`overall_status`は`needs_visual_review`です。空マスクや解像度の不一致はエラーにします。PNG出力のみを使用します。

## 起動

Python 3.11以上。GPUなしでも切り抜き・色変更・合成・テストは動作します。

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python examples/create_sample.py
design-edit run examples/recolor.json
design-edit run examples/extract.json
python -m pytest -q
```

サンプルはこのリポジトリで作成した幾何学ロボットです。「胸の丸い表示灯の色だけを変更」「表示灯を小さい四角に変更」を例にし、既存作品の素材を必要としません。

### マスク作成

領域JSONの座標は元画像の画素座標。矩形は`[left, top, right, bottom]`で右・下端を含みません。

```json
{"boxes": [[224, 360, 289, 425]], "polygons": []}
```

```sh
design-edit mask examples/robot.png regions.json mask.png
design-edit run request.json --output runs
```

```json
{
  "mode": "recolor",
  "source": "input.png",
  "editable_mask": "mask.png",
  "protected_mask": "protected.png",
  "hue": 0,
  "feather": 2,
  "instruction": "Change only the status indicator to red",
  "protected_constraints": ["Preserve silhouette, position and other colors"]
}
```

素材パスは依頼JSONからの相対パス。保護マスクの非ゼロ領域は編集マスクより優先します。参照マスクは保存される参考情報で、生成制御には未使用です。フェザーは許可領域の内側だけに適用し、外へ広げません。パレット画像はRGBAへ正規化して比較し、EXIF回転やICC変換は自動適用しません。高ビット深度・アニメーション画像は対象外です。

## ローカルInpainting

[セットアップ](docs/comfyui.md)を参照してください。ComfyUIを`127.0.0.1:8188`で起動後：

```sh
design-edit run examples/inpaint.json
```

この四角化サンプルは形状の追従品質を検証する実験用で、現在は目視評価で不合格です。実行確認済みの単純な除去編集は`design-edit run examples/remove-indicator.json`で試せます。具体的な成功・失敗画像は検証記録に掲載しています。

画像・マスクをアップロードし、`/prompt`→`/history/{id}`→`/view`で結果を取得します。[ComfyUI公式API](https://docs.comfy.org/development/comfyui-server/comms_routes)に基づくコアノードのみの構成です。キャンバスは8の倍数へ右下パディングし、元サイズへ切り戻すため、座標やサイズを拡縮しません。生成候補のAlphaは原画像に戻してから合成します。

有料サービス・従量API・Photoshopは不要です。モデルの重みは同梱せず、各モデルのライセンスを別途適用します。コードのMITライセンスはモデルへ適用されません。

## 品質と履歴

各`runs/<id>/`に`request.json`、原画像、マスク、候補、結果、`comparison.png`（原画像・結果・差分の順）、`validation.json`を保存します。ComfyUI実行時は実際のワークフロー・実行履歴・環境情報も記録します。エラー時は`failure.json`を保存します。実行履歴はローカルに置き、Gitには含めません。生成の完全再現性はGPU・モデル・ComfyUIの版にも依存するため、seedだけでは保証しません。

編集の基準は採用済みの原画像です。候補を自動で次の基準へ昇格しません。形・位置・大きさ・比率・色・表情を別の変更軸として管理し、一回の編集を狭く限定します。表示サイズと拡大画像の両方でマスク内の形状・境界を確認してください。

## 今後の段階

Phase 1の実画像レビューを通過してから、マスク精度、パラメータ調整、ControlNet、SDXL、他のローカルモデルの順に必要性を判断します。Phase 2/3の自然言語解釈・自動検出・IoU/Hausdorff・ランドマーク・左右対称・複数視点照合・条件付き再試行・モデル比較は未実装です。無制限の自動再生成は行いません。タイムアウト時のジョブはComfyUIに残る可能性があり、記録したIDで確認します。

複数方向の将来仕様では物体自身の左右、同尺度・同投影、遮蔽と取り付け位置を記録します。2Dから検証できない奥行きは推定とし、他視点を勝手に再生成しません。新規生成は局所編集とは別操作として扱い、現CLIでは提供しません。

開発・検証状況は[検証記録](docs/validation.md)を参照してください。
