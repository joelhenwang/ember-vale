//! The hearth palette, the animated title and the rising embers.

use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

pub const BG: Color = Color::Rgb(22, 15, 13);
pub const PANEL: Color = Color::Rgb(30, 21, 18);
pub const SELECTED: Color = Color::Rgb(62, 36, 26);
pub const BORDER: Color = Color::Rgb(112, 66, 44);
pub const BORDER_HOT: Color = Color::Rgb(214, 112, 52);
pub const EMBER: Color = Color::Rgb(255, 128, 48);
pub const FLAME: Color = Color::Rgb(255, 190, 92);
pub const GOLD: Color = Color::Rgb(236, 198, 122);
pub const PARCHMENT: Color = Color::Rgb(238, 224, 200);
pub const ASH: Color = Color::Rgb(150, 136, 128);
pub const SMOKE: Color = Color::Rgb(96, 84, 78);
pub const MOSS: Color = Color::Rgb(140, 204, 112);
pub const BLOOD: Color = Color::Rgb(236, 92, 76);
pub const SKY: Color = Color::Rgb(132, 176, 220);

pub const SPINNER: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

pub fn spinner(tick: u64) -> &'static str {
    SPINNER[(tick as usize / 2) % SPINNER.len()]
}

const TITLE: [&str; 2] = [
    "█▀▀ █▀▄▀█ █▄▄ █▀▀ █▀█   █ █ ▄▀█ █   █▀▀",
    "██▄ █ ▀ █ █▄█ ██▄ █▀▄   ▀▄▀ █▀█ █▄▄ ██▄",
];

fn mix(a: (f32, f32, f32), b: (f32, f32, f32), t: f32) -> (f32, f32, f32) {
    (
        a.0 + (b.0 - a.0) * t,
        a.1 + (b.1 - a.1) * t,
        a.2 + (b.2 - a.2) * t,
    )
}

fn rgb(c: (f32, f32, f32), light: f32) -> Color {
    let f = |v: f32| (v * light).clamp(0.0, 255.0) as u8;
    Color::Rgb(f(c.0), f(c.1), f(c.2))
}

/// Gold through ember to deep red, left to right, gently flickering.
fn fire(t: f32, flicker: f32) -> Color {
    let gold = (255.0, 220.0, 130.0);
    let ember = (255.0, 128.0, 48.0);
    let red = (210.0, 60.0, 44.0);
    let c = if t < 0.5 {
        mix(gold, ember, t * 2.0)
    } else {
        mix(ember, red, (t - 0.5) * 2.0)
    };
    rgb(c, 0.88 + 0.12 * flicker)
}

/// The two-row block-letter title, centred in `area`.
pub fn title_lines(tick: u64) -> Vec<Line<'static>> {
    TITLE
        .iter()
        .enumerate()
        .map(|(row, text)| {
            let width = text.chars().count() as f32;
            let spans = text.chars().enumerate().map(|(col, ch)| {
                let phase = tick as f32 * 0.18 + col as f32 * 0.45 + row as f32;
                let flicker = (phase.sin() + 1.0) / 2.0;
                let mut color = fire(col as f32 / width, flicker);
                if row == 1
                    && let Color::Rgb(r, g, b) = color
                {
                    color = Color::Rgb(r, (g as f32 * 0.82) as u8, (b as f32 * 0.8) as u8);
                }
                Span::styled(
                    ch.to_string(),
                    Style::new().fg(color).add_modifier(Modifier::BOLD),
                )
            });
            Line::from(spans.collect::<Vec<_>>()).centered()
        })
        .collect()
}

pub const TITLE_WIDTH: u16 = 39;

struct Spark {
    x: f32,
    y: f32,
    drift: f32,
    speed: f32,
    life: f32,
    max: f32,
}

/// Sparks rising from the bottom of the header, cooling as they climb.
#[derive(Default)]
pub struct Embers {
    sparks: Vec<Spark>,
}

impl Embers {
    pub fn tick(&mut self, area: Rect) {
        if area.width == 0 || area.height == 0 {
            return;
        }
        let wanted = (area.width as usize / 5).clamp(6, 40);
        if self.sparks.len() < wanted && fastrand::u8(0..3) == 0 {
            let max = 14.0 + fastrand::f32() * 22.0;
            self.sparks.push(Spark {
                x: fastrand::f32() * area.width as f32,
                y: area.height as f32 - 0.5,
                drift: (fastrand::f32() - 0.5) * 0.25,
                speed: 0.12 + fastrand::f32() * 0.22,
                life: max,
                max,
            });
        }
        for spark in &mut self.sparks {
            spark.y -= spark.speed;
            spark.x += spark.drift + (spark.y * 0.7).sin() * 0.06;
            spark.life -= 1.0;
        }
        self.sparks.retain(|s| s.life > 0.0 && s.y >= 0.0);
    }

    pub fn draw(&self, area: Rect, buf: &mut Buffer) {
        for spark in &self.sparks {
            let (x, y) = (spark.x.round(), spark.y.floor());
            if x < 0.0 || y < 0.0 || x >= area.width as f32 || y >= area.height as f32 {
                continue;
            }
            let heat = spark.life / spark.max;
            let (glyph, color) = match heat {
                h if h > 0.75 => ("✦", Color::Rgb(255, 214, 120)),
                h if h > 0.5 => ("•", Color::Rgb(255, 150, 60)),
                h if h > 0.25 => ("·", Color::Rgb(210, 82, 44)),
                _ => ("˙", Color::Rgb(110, 62, 48)),
            };
            if let Some(cell) = buf.cell_mut((area.x + x as u16, area.y + y as u16))
                && cell.symbol() == " "
            {
                cell.set_symbol(glyph).set_fg(color);
            }
        }
    }
}

/// A key cap such as ` Enter ` followed by what it does.
pub fn key<'a>(cap: &'a str, action: &'a str) -> Vec<Span<'a>> {
    vec![
        Span::styled(
            format!(" {cap} "),
            Style::new().fg(BG).bg(GOLD).add_modifier(Modifier::BOLD),
        ),
        Span::styled(format!(" {action}   "), Style::new().fg(ASH)),
    ]
}

/// A progress bar drawn with blocks, glowing from gold to ember.
pub fn bar(width: u16, ratio: f64, tick: u64) -> Line<'static> {
    let width = width as usize;
    let filled = ((width as f64) * ratio.clamp(0.0, 1.0)).round() as usize;
    let mut spans = Vec::with_capacity(width);
    for i in 0..width {
        if i < filled {
            let t = i as f32 / width.max(1) as f32;
            let flicker = ((tick as f32 * 0.3 - i as f32 * 0.4).sin() + 1.0) / 2.0;
            spans.push(Span::styled("█", Style::new().fg(fire(t * 0.6, flicker))));
        } else {
            spans.push(Span::styled("░", Style::new().fg(SMOKE)));
        }
    }
    Line::from(spans)
}
