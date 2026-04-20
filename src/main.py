"""
ニュース収集・要約・配信のメインスクリプト
- 設定ファイル（config/feeds.yml）から各カテゴリのRSSフィードを取得
- 過去24時間以内の記事を収集
- Claude API（任意）で要約を生成
- HTML/Markdown形式で出力
- メール送信（任意）
"""

import os
import sys
import yaml
import feedparser
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import hashlib

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Article:
    """記事データクラス"""
    title: str
    link: str
    summary: str
    published: datetime
    source: str
    category: str
    category_name: str
    ai_summary: Optional[str] = None

    @property
    def hash_id(self) -> str:
        """記事のユニークID（URL基準）"""
        return hashlib.md5(self.link.encode()).hexdigest()[:12]


class NewsCollector:
    """RSSフィードからニュースを収集する"""

    def __init__(self, config_path: str = "config/feeds.yml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.settings = self.config["settings"]

    def collect_all(self) -> list[Article]:
        """全カテゴリから記事を収集"""
        all_articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.settings["hours_lookback"]
        )

        for cat_key, cat_data in self.config["categories"].items():
            logger.info(f"カテゴリ収集開始: {cat_data['name']}")
            cat_articles = []

            for feed_info in cat_data["feeds"]:
                try:
                    articles = self._parse_feed(
                        feed_info, cat_key, cat_data["name"], cutoff
                    )
                    cat_articles.extend(articles)
                    logger.info(f"  {feed_info['name']}: {len(articles)}件")
                except Exception as e:
                    logger.warning(f"  {feed_info['name']} 取得失敗: {e}")

            # 公開日時の新しい順にソート、カテゴリごとに上限を適用
            cat_articles.sort(key=lambda a: a.published, reverse=True)
            cat_articles = cat_articles[: self.settings["max_articles_per_category"]]
            all_articles.extend(cat_articles)

        # 全体の上限を適用
        all_articles.sort(key=lambda a: a.published, reverse=True)
        return all_articles[: self.settings["max_articles_total"]]

    def _parse_feed(
        self, feed_info: dict, cat_key: str, cat_name: str, cutoff: datetime
    ) -> list[Article]:
        """個別のRSSフィードをパース"""
        parsed = feedparser.parse(feed_info["url"])
        articles = []

        for entry in parsed.entries:
            published = self._extract_datetime(entry)
            if published is None or published < cutoff:
                continue

            articles.append(
                Article(
                    title=entry.get("title", "無題").strip(),
                    link=entry.get("link", ""),
                    summary=self._clean_summary(entry.get("summary", "")),
                    published=published,
                    source=feed_info["name"],
                    category=cat_key,
                    category_name=cat_name,
                )
            )
        return articles

    @staticmethod
    def _extract_datetime(entry) -> Optional[datetime]:
        """エントリから公開日時を取り出す"""
        for key in ("published_parsed", "updated_parsed"):
            time_struct = entry.get(key)
            if time_struct:
                return datetime(*time_struct[:6], tzinfo=timezone.utc)
        return None

    @staticmethod
    def _clean_summary(html: str, max_len: int = 300) -> str:
        """HTMLタグを除去して要約を整える"""
        import re
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_len] + ("..." if len(text) > max_len else "")


class AISummarizer:
    """Claude APIで日本語要約を生成（任意機能）"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.enabled = bool(self.api_key)
        if self.enabled:
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                logger.warning("anthropic ライブラリ未インストール。要約はスキップ")
                self.enabled = False

    def summarize_batch(self, articles: list[Article]) -> None:
        """記事を一括で日本語要約（インプレース更新）"""
        if not self.enabled:
            logger.info("AI要約は無効（APIキー未設定）")
            return

        logger.info(f"AI要約開始: {len(articles)}件")
        for article in articles:
            try:
                article.ai_summary = self._summarize_one(article)
            except Exception as e:
                logger.warning(f"要約失敗 [{article.title[:30]}]: {e}")

    def _summarize_one(self, article: Article) -> str:
        """1記事を日本語で2-3文に要約"""
        prompt = f"""以下のニュース記事を、エンジニア向けに日本語で2-3文にまとめてください。
技術的な要点を優先し、結論から書いてください。装飾や前置きは不要です。

タイトル: {article.title}
内容: {article.summary}
"""
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


class HTMLRenderer:
    """HTMLレポート生成"""

    def render(self, articles: list[Article], output_path: Path) -> None:
        today = datetime.now().strftime("%Y年%m月%d日")

        # カテゴリごとにグルーピング
        grouped: dict[str, list[Article]] = {}
        for article in articles:
            grouped.setdefault(article.category_name, []).append(article)

        html = self._build_html(today, grouped, len(articles))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML出力: {output_path}")

    def _build_html(self, date_str: str, grouped: dict, total: int) -> str:
        # カテゴリセクションを構築
        sections = []
        for cat_name, articles in grouped.items():
            items = "\n".join(self._render_article(a) for a in articles)
            sections.append(f"""
        <section class="category" data-category="{cat_name}">
          <h2>{cat_name} <span class="count">{len(articles)}</span></h2>
          <div class="articles">{items}</div>
        </section>""")

        sections_html = "\n".join(sections)

        # フィルターボタン（カテゴリ一覧）
        filter_buttons = '<button class="filter-btn active" data-filter="all">すべて</button>'
        for cat_name, articles in grouped.items():
            filter_buttons += (
                f'<button class="filter-btn" data-filter="{cat_name}">'
                f'{cat_name} <span class="count">{len(articles)}</span></button>'
            )

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tech News Daily - {date_str}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", sans-serif;
      line-height: 1.7; color: #1a1a1a; background: #f5f7fa;
      padding: 2rem 1rem;
    }}
    .container {{ max-width: 860px; margin: 0 auto; }}
    header {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white; padding: 2rem; border-radius: 12px; margin-bottom: 2rem;
    }}
    header h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
    header .meta {{ opacity: 0.9; font-size: 0.95rem; }}
    .category {{
      background: white; border-radius: 12px; padding: 1.5rem 2rem;
      margin-bottom: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .category h2 {{
      font-size: 1.3rem; color: #2c3e50; padding-bottom: 0.75rem;
      border-bottom: 2px solid #edf2f7; margin-bottom: 1rem;
      display: flex; align-items: center; gap: 0.75rem;
    }}
    .count {{
      background: #667eea; color: white; font-size: 0.75rem;
      padding: 0.2rem 0.6rem; border-radius: 999px; font-weight: normal;
    }}
    .article {{ padding: 1rem 0; border-bottom: 1px solid #f0f0f0; }}
    .article:last-child {{ border-bottom: none; }}
    .article h3 {{ font-size: 1.05rem; margin-bottom: 0.4rem; }}
    .article h3 a {{ color: #2c5282; text-decoration: none; }}
    .article h3 a:hover {{ text-decoration: underline; }}
    .article .source {{ font-size: 0.85rem; color: #718096; margin-bottom: 0.5rem; }}
    .article .summary {{ font-size: 0.95rem; color: #4a5568; }}
    .ai-badge {{
      display: inline-block; background: #e6fffa; color: #234e52;
      font-size: 0.7rem; padding: 0.1rem 0.4rem; border-radius: 4px;
      margin-right: 0.4rem;
    }}
    footer {{ text-align: center; padding: 2rem 0; color: #718096; font-size: 0.85rem; }}
    .filter-bar {{
      position: sticky; top: 0; z-index: 10;
      background: rgba(245, 247, 250, 0.95); backdrop-filter: blur(8px);
      padding: 1rem 0; margin: -1rem 0 1.5rem; border-bottom: 1px solid #e2e8f0;
    }}
    .filter-search {{
      width: 100%; padding: 0.6rem 1rem; font-size: 0.95rem;
      border: 1px solid #cbd5e0; border-radius: 8px; margin-bottom: 0.75rem;
      background: white;
    }}
    .filter-search:focus {{ outline: none; border-color: #667eea; }}
    .filter-buttons {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
    .filter-btn {{
      padding: 0.4rem 0.9rem; font-size: 0.85rem; cursor: pointer;
      background: white; border: 1px solid #cbd5e0; border-radius: 999px;
      color: #4a5568; display: inline-flex; align-items: center; gap: 0.4rem;
      transition: all 0.15s;
    }}
    .filter-btn:hover {{ border-color: #667eea; color: #667eea; }}
    .filter-btn.active {{
      background: #667eea; border-color: #667eea; color: white;
    }}
    .filter-btn.active .count {{ background: rgba(255,255,255,0.3); }}
    .filter-btn .count {{
      background: #edf2f7; color: inherit; font-size: 0.7rem;
      padding: 0.1rem 0.5rem; border-radius: 999px;
    }}
    .no-results {{
      text-align: center; padding: 3rem 1rem; color: #718096;
      background: white; border-radius: 12px;
    }}
    .category.hidden, .article.hidden {{ display: none; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>📰 Tech News Daily</h1>
      <div class="meta">{date_str} / 全{total}件</div>
    </header>
    <div class="filter-bar">
      <input type="search" class="filter-search" id="searchInput" placeholder="🔍 タイトル・要約・配信元で検索...">
      <div class="filter-buttons">{filter_buttons}</div>
    </div>
    {sections_html}
    <div class="no-results" id="noResults" style="display:none;">該当する記事がありません</div>
    <footer>Powered by GitHub Actions + Claude API</footer>
  </div>
  <script>
    (function() {{
      const searchInput = document.getElementById('searchInput');
      const noResults = document.getElementById('noResults');
      const buttons = document.querySelectorAll('.filter-btn');
      const categories = document.querySelectorAll('.category');
      let activeFilter = 'all';

      function applyFilter() {{
        const keyword = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;

        categories.forEach(cat => {{
          const catName = cat.dataset.category;
          const catMatch = activeFilter === 'all' || activeFilter === catName;
          let catVisible = 0;

          cat.querySelectorAll('.article').forEach(art => {{
            const text = art.textContent.toLowerCase();
            const kwMatch = !keyword || text.includes(keyword);
            const show = catMatch && kwMatch;
            art.classList.toggle('hidden', !show);
            if (show) catVisible++;
          }});

          cat.classList.toggle('hidden', catVisible === 0);
          visibleCount += catVisible;
        }});

        noResults.style.display = visibleCount === 0 ? 'block' : 'none';
      }}

      buttons.forEach(btn => {{
        btn.addEventListener('click', () => {{
          buttons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          activeFilter = btn.dataset.filter;
          applyFilter();
        }});
      }});

      searchInput.addEventListener('input', applyFilter);
    }})();
  </script>
</body>
</html>"""

    @staticmethod
    def _render_article(a: Article) -> str:
        summary_html = ""
        if a.ai_summary:
            summary_html = f'<p class="summary"><span class="ai-badge">AI要約</span>{a.ai_summary}</p>'
        elif a.summary:
            summary_html = f'<p class="summary">{a.summary}</p>'

        time_str = a.published.astimezone().strftime("%m/%d %H:%M")
        return f"""
      <article class="article">
        <h3><a href="{a.link}" target="_blank" rel="noopener">{a.title}</a></h3>
        <div class="source">{a.source} · {time_str}</div>
        {summary_html}
      </article>"""


def main():
    logger.info("=== Tech News Bot 開始 ===")

    # 1. 収集
    collector = NewsCollector("config/feeds.yml")
    articles = collector.collect_all()
    logger.info(f"収集完了: 全{len(articles)}件")

    if not articles:
        logger.warning("記事が1件も収集できませんでした")
        sys.exit(0)

    # 2. AI要約（APIキーがある場合のみ）
    if collector.settings.get("enable_ai_summary", False):
        summarizer = AISummarizer()
        summarizer.summarize_batch(articles)

    # 3. HTML出力
    today = datetime.now().strftime("%Y-%m-%d")
    renderer = HTMLRenderer()
    renderer.render(articles, Path(f"docs/index.html"))
    renderer.render(articles, Path(f"docs/archive/{today}.html"))

    logger.info("=== 完了 ===")


if __name__ == "__main__":
    main()
