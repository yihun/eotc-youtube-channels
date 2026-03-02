# YouTube Channel Performance Analysis

## Overview

This document describes the methodology behind three core YouTube performance analyses applied to a dataset containing video-level metrics (views, likes, comments, publish timestamps) across two channels.

**Dataset Fields:**

| Field          | Description                     |
| -------------- | ------------------------------- |
| `video_id`     | Unique YouTube video identifier |
| `channel`      | Channel identifier (1 or 2)     |
| `title`        | Video title                     |
| `published_at` | UTC timestamp of publication    |
| `views`        | Total view count                |
| `likes`        | Total like count                |
| `comments`     | Total comment count             |
| `last_updated` | Timestamp of data collection    |

## Engagement Analysis

### What It Measures
Engagement analysis quantifies how actively viewers interact with content relative to how many people watch it. A video can have high views but low engagement (passive audience) or low views but high engagement (niche but dedicated audience). Both patterns carry strategic insight.

### Metrics

| Metric              | Formula                      | Interpretation                      |
| ------------------- | ---------------------------- | ----------------------------------- |
| **Like Rate**       | `likes / views`              | Proportion of viewers who liked     |
| **Comment Rate**    | `comments / views`           | Proportion of viewers who commented |
| **Engagement Rate** | `(likes + comments) / views` | Overall interaction rate            |

### Interpretation Guide

- **Engagement rate > 5%** — strong audience connection
- **Engagement rate 2–5%** — typical for religious/liturgical content
- **Engagement rate < 1%** — passive viewership, content may not be resonating

## Low Engagement Flags
### What It Measures

This analysis identifies videos that deviate significantly from the channel's typical performance pattern. It surfaces four types of anomalies:

| Flag                           | Meaning                                                                             |
| ------------------------------ | ----------------------------------------------------------------------------------- |
| **High Views, Low Engagement** | Many viewers but little interaction — audience may be passive or content misaligned |
| **Low Views, High Engagement** | Small but highly engaged audience — potential niche content worth promoting         |
| **Top Performer**              | High on both dimensions — replicate this content                                    |
| **Underperformer**             | Low on both dimensions — review for quality or distribution issues                  |
| **Normal**                     | Within expected range                                                               |
### How Z-Scores Work

A **z-score** measures how far a value is from the channel's mean, in units of standard deviation:

```
z = (value - mean) / standard_deviation
```

- `z > 1` means the video is **above average** (top ~16%)
- `z < -1` means the video is **below average** (bottom ~16%)
- Calculated **per channel** so each channel is benchmarked against itself

## Running All Three Analyses End-to-End