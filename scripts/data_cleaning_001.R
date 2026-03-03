# Loading libraries

library(DBI)
library(RSQLite)
library(dplyr)
library(stringr)
# set plot background
dark_gregy = "#1e2a45"
# Dallas Debre Miheret St Micheal=1 and Debre Berhan Holy Trinity EOTC=2
mydb_conn <- dbConnect(RSQLite::SQLite(), "eotc_youtube_data.db")

videos <- dbGetQuery(mydb_conn, "SELECT * FROM videos;") |>
  dplyr::mutate(published_at = lubridate::ymd_hms(published_at, tz = "UTC")) |>
  dplyr::filter(channel == 2) # Holy Trinity church
comments <- dbGetQuery(mydb_conn, "SELECT * FROM comments;")
channel_stats <- dbGetQuery(mydb_conn, "SELECT * FROM channels;")

comments <- comments |>
  dplyr::filter(video_id %in% videos$video_id)

channel_stats <- channel_stats |>
  dplyr::filter(channel == 2) # Holy Trinity church

# close connection
dbDisconnect(mydb_conn)

# Cleaning
extract_english_text <- function(text) {
  # Extract words with English letters or numbers
  matches <- stringr::str_extract_all(text, "[A-Za-z0-9 ]+")[[1]]
  english_text <- stringr::str_squish(paste(matches, collapse = " "))

  # If nothing extracted (i.e., just empty), return original
  if (english_text == "") {
    return(text)
  }

  return(english_text)
}
videos <- videos |>
  mutate(
    service_themes = title |>
      str_remove_all("http[s]?://\\S+") |> # Remove URLs
      str_remove_all("[[:digit:]]+") |> # Remove numbers
      #str_remove_all("[A-Za-z]+") |>              # Remove English
      str_remove_all("[[:punct:]]") |> # Remove punctuation
      str_remove_all("[\\p{So}\\p{Cn}]") |> # Remove symbols/emojis
      str_squish() # Remove extra spaces
  ) |>
  mutate(
    service_cat = case_when(
      str_detect(service_themes, "ጸሎተ ቅዳሴ|ቅዳሴ|Kidase") ~
        "Divine Liturgy (Qidase)",
      str_detect(service_themes, "መዝሙር") ~ "Mezmur (Hymns) ",
      str_detect(service_themes, "ሥርዓተ ማኅሌት|^ማኅሌት|ማኅሌት|Mahlet") ~
        "Mahlet (Chanting)",
      str_detect(service_themes, "Celebration|celeb|ጥምቀት|ታቦር|ዋዜማ|Wazema") ~
        "Feast Day Celebration",
      str_detect(service_themes, "^ማኅሌተ|Tsige|ጽጌ") ~ "Mahilete Tsegie",
      .default = NA_character_
    )
  ) |>
  rowwise() |>
  mutate(
    service_cat = case_when(
      str_detect(
        service_themes,
        "sermon|Sermon|ንግሥ|Service|service|ወንጌል|ሰዓታት"
      ) ~
        "Sermon/Teaching",
      str_detect(service_themes, "ምልጣን") ~ "Miltan",
      str_detect(
        service_themes,
        "ሕማማት|ነነዌ|ወረብ|ዳግም|ፋሲካ|አርያም|የሆሣዕና|አርያም|ዘዕርገት|ትንሣኤ|ስዑር|ሥዑር|የስቅለት|ስቅለት"
      ) ~
        "Easter Season",
      str_detect(service_themes, "ውዳሴ") ~ "Wudasie Mariam",
      str_detect(service_themes, "ዘሠርክ|ሠርክ") ~ "Tselot Zeserk",
      .default = "Other Services"
    )
  ) |>
  ungroup()

videos <- videos |>
  mutate(service_clean = purrr::map_chr(title, extract_english_text)) |>
  mutate(source_url = paste0("https://www.youtube.com/watch?v=", video_id)) |>
  mutate(
    like_rate = likes / views,
    comment_rate = comments / views,
    engage_rate = (likes + comments) / views
  ) |>
  mutate(
    # published_at_hr = ymd_hms(published_at),
    hour_of_day = hour(published_at),
    day_of_week = wday(published_at, label = TRUE, abbr = FALSE),
    month = month(published_at, label = TRUE)
  ) |>
  filter(views > 0) |>
  mutate(
    z_views = scale(views)[, 1],
    z_engage = scale(engage_rate)[, 1]
  ) |>
  mutate(
    flag = case_when(
      z_views > 1 & z_engage < -1 ~ "High Views, Low Engagement",
      z_views < -1 & z_engage > 1 ~ "Low Views, High Engagement",
      z_views > 1 & z_engage > 1 ~ "Top Performer",
      z_views < -1 & z_engage < -1 ~ "Underperformer",
      TRUE ~ "Normal"
    )
  )
