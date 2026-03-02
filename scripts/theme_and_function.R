# Function for custom theme ggplot2 theme

custom_theme <- function() {
  theme(
    panel.background = element_rect(fill = dark_gregy),
    plot.background = element_rect(fill = dark_gregy, color = dark_gregy),
    panel.grid.minor.y = element_blank(), # Remove minor y-axis grid lines
    panel.grid.major.y = element_line(color = "#605e5eff"),
    panel.grid.minor.x = element_blank(), # Remove minor x-axis grid lines
    panel.grid.major.x = element_line(color = "#605e5eff"),
    plot.title = element_text(hjust = 0.5, face = 'bold'),
    text = element_text(size = 12, color = "white"),
    axis.ticks = element_blank(),
    axis.text.y = element_text(color = "white"),
    strip.text = element_text(color = "white"),
    axis.title.y = element_text(colour = "white", size = 12),
    axis.title.x = element_text(color = "white"),
    axis.text.x = element_text(color = "white"),
    strip.background = element_rect(fill = "#E2E6ED50", color = "white"),
  )
}
