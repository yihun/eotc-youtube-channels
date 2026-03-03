# Function for custom theme ggplot2 theme
library(ggplot2)
custom_theme <- function() {
  dark_gregy = "#1e2a45"
  theme(
    panel.background = element_rect(fill = dark_gregy),
    plot.background = element_rect(fill = dark_gregy, color = dark_gregy),
    panel.grid.minor.y = element_blank(), # Remove minor y-axis grid lines
    panel.grid.major.y = element_line(color = "#30384d", linewidth = 0.05),
    panel.grid.minor.x = element_blank(), # Remove minor x-axis grid lines
    panel.grid.major.x = element_line(color = "#30384d", linewidth = 0.05),
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
