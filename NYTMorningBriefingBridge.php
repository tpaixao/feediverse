<?php

class NYTMorningBriefingBridge extends FeedExpander
{
    const MAINTAINER = 'nanobot';
    const NAME = 'NYT The Morning Briefing';
    const URI = 'https://www.nytimes.com/series/us-morning-briefing';
    const CACHE_TIMEOUT = 900; // 15 minutes
    const DESCRIPTION = 'The Morning newsletter from the New York Times';

    // static.nytimes.com hosts a free, full-text version of the latest
    // Morning briefing (no paywall). It always reflects the most recent
    // issue. Older issues are not accessible via a predictable URL.
    const SAMPLE_URL = 'https://static.nytimes.com/email-content/NN_sample.html';
    const TWITTER_UA = 'Mozilla/5.0 (compatible; Twitterbot/1.0)';

    public function collectData()
    {
        $url = 'https://www.nytimes.com/svc/collections/v1/publish/https://www.nytimes.com/series/us-morning-briefing/rss.xml';
        $this->collectExpandableDatas($url, 20);
    }

    protected function parseItem(array $item)
    {
        // Fetch the static sample page once to get full text for the latest briefing
        static $sampleHtml = null;
        static $sampleTitle = null;
        static $sampleParagraphs = null;

        if ($sampleHtml === null) {
            try {
                $sampleHtml = getContents(self::SAMPLE_URL, ['User-Agent: ' . self::TWITTER_UA]);
                $sampleDoc = str_get_html($sampleHtml);
                if ($sampleDoc) {
                    $titleEl = $sampleDoc->find('h1', 0);
                    if (!$titleEl) {
                        $titleEl = $sampleDoc->find('title', 0);
                    }
                    if ($titleEl) {
                        // Strip "The Morning: " prefix if present
                        $sampleTitle = trim($titleEl->plaintext);
                        $sampleTitle = preg_replace('/^The Morning:\s*/i', '', $sampleTitle);
                    }

                    // Extract all substantive paragraphs as full-text content
                    $paragraphs = [];
                    foreach ($sampleDoc->find('p') as $p) {
                        $text = trim($p->plaintext);
                        // Skip boilerplate paragraphs (signoff, subscribe, unsubscribe, etc.)
                        if (strlen($text) < 30) continue;
                        if (preg_match('/^(Thanks for spending|Sign up here|Reach our team|Need help|You received this|To stop receiving|Subscribe to The Times|Change Your Email|The New York Times Company)/i', $text)) continue;
                        if (preg_match('/^(Editor:|News Editor:|Associate Editor:|News Staff:|Saturday Writer:|Editorial Director)/i', $text)) continue;
                        $paragraphs[] = '<p>' . $p->innertext . '</p>';
                    }
                    $sampleParagraphs = implode("\n", $paragraphs);
                }
            } catch (\Throwable $e) {
                $sampleHtml = false;
            }
        }

        // Check if this RSS item matches the sample page (latest briefing)
        $itemTitle = $item['title'] ?? '';
        $isLatest = false;
        if ($sampleTitle !== null && $itemTitle !== '') {
            // Fuzzy match: the RSS title may differ slightly from the sample title
            // RSS: "The Viceroy of Venezuela" -> sample: "The viceroy of Venezuela"
            if (strcasecmp($itemTitle, $sampleTitle) === 0) {
                $isLatest = true;
            } elseif (stripos($sampleTitle, $itemTitle) !== false || stripos($itemTitle, $sampleTitle) !== false) {
                $isLatest = true;
            }
        }

        if ($isLatest && !empty($sampleParagraphs)) {
            // Rewrite link to the free full-text version and embed the content
            $item['uri'] = self::SAMPLE_URL;
            $item['content'] = $sampleParagraphs;

            // Extract og:image from the sample page
            if ($sampleDoc) {
                $ogImage = $sampleDoc->find('meta[property="og:image"]', 0);
                if ($ogImage && $ogImage->content) {
                    $item['enclosures'] = [$ogImage->content];
                }
            }
            return $item;
        }

        // For older items: fetch the article page with Twitterbot UA
        // to get og:description and og:image ( richer than raw RSS )
        try {
            $html = getContents($item['uri'], ['User-Agent: ' . self::TWITTER_UA]);
            $doc = str_get_html($html);
            if ($doc) {
                $ogImage = $doc->find('meta[property="og:image"]', 0);
                if ($ogImage && $ogImage->content) {
                    $item['enclosures'] = [$ogImage->content];
                }
                $ogDesc = $doc->find('meta[property="og:description"]', 0);
                if ($ogDesc && $ogDesc->content) {
                    $desc = $ogDesc->content;
                    if (strlen($desc) > strlen($item['content'] ?? '')) {
                        $item['content'] = '<p>' . htmlspecialchars($desc, ENT_QUOTES) . '</p>';
                    }
                }
            }
        } catch (\Throwable $e) {
            // Return item as-is on fetch failure
        }

        return $item;
    }
}