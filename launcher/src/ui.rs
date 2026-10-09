//! Drawing every screen.

use ratatui::Frame;
use ratatui::layout::{Alignment, Constraint, Layout, Margin, Rect};
use ratatui::style::{Color, Style, Stylize};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Clear, Paragraph, Wrap};

use crate::app::{App, Item, SECTIONS, Screen, Tone};
use crate::backups::{self, Backup};
use crate::checks::Status;
use crate::config::{self, Storyteller};
use crate::services::{Source, StepState};
use crate::theme::{self, *};

const MIN_W: u16 = 64;
const MIN_H: u16 = 22;
pub const HEADER_H: u16 = 7;

pub fn header_area(area: Rect) -> Rect {
    Rect {
        height: HEADER_H.min(area.height),
        ..area
    }
}

pub fn draw(frame: &mut Frame, app: &App) {
    let area = frame.area();
    frame.render_widget(Block::new().style(Style::new().bg(BG).fg(PARCHMENT)), area);
    if area.width < MIN_W || area.height < MIN_H {
        return too_small(frame, area);
    }
    let [head, body, foot] = Layout::vertical([
        Constraint::Length(HEADER_H),
        Constraint::Min(8),
        Constraint::Length(2),
    ])
    .areas(area);
    header(frame, app, head);
    let body = body.inner(Margin::new(2, 0));
    match app.screen {
        Screen::Checks => checks_screen(frame, app, body),
        Screen::Settings => settings_screen(frame, app, body),
        Screen::Launch => launch_screen(frame, app, body),
        Screen::Playing => playing_screen(frame, app, body),
        Screen::Backups => backups_screen(frame, app, body),
        Screen::Closing => closing_screen(frame, app, body),
    }
    footer(frame, app, foot);
}

fn too_small(frame: &mut Frame, area: Rect) {
    let text = vec![
        Line::from("✦ Ember Vale ✦".fg(EMBER).bold()),
        Line::from(""),
        Line::from("Please make this window a little bigger.".fg(PARCHMENT)),
        Line::from(
            format!(
                "({}×{} now, {MIN_W}×{MIN_H} needed)",
                area.width, area.height
            )
            .fg(ASH),
        ),
    ];
    let h = text.len() as u16;
    let y = area.y + area.height.saturating_sub(h) / 2;
    frame.render_widget(
        Paragraph::new(text).alignment(Alignment::Center),
        Rect {
            y,
            height: h.min(area.height),
            ..area
        },
    );
}

fn header(frame: &mut Frame, app: &App, area: Rect) {
    let tagline = match app.screen {
        Screen::Checks => "~ gear check before the journey ~",
        Screen::Settings => "~ settings ~",
        Screen::Launch => "~ lighting the hearth ~",
        Screen::Playing => "~ the vale is awake ~",
        Screen::Backups => "~ backups of your stories ~",
        Screen::Closing => "~ banking the fire ~",
    };
    let mut lines = vec![Line::from(""), Line::from("")];
    if area.width >= theme::TITLE_WIDTH + 4 {
        lines.extend(theme::title_lines(app.tick));
    } else {
        lines.push(Line::from("EMBER VALE".fg(EMBER).bold()).centered());
        lines.push(Line::from(""));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(tagline.fg(GOLD).italic()).centered());
    frame.render_widget(Paragraph::new(lines), area);
    app.embers.draw(area, frame.buffer_mut());
}

fn panel(title: &str, hot: bool) -> Block<'_> {
    Block::new()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::new().fg(if hot { BORDER_HOT } else { BORDER }))
        .title(Line::from(vec![
            " ".into(),
            title.fg(FLAME).bold(),
            " ".into(),
        ]))
        .style(Style::new().bg(PANEL))
}

fn status_icon(status: Status, tick: u64) -> Span<'static> {
    match status {
        Status::Waiting => Span::styled(theme::spinner(tick), Style::new().fg(EMBER)),
        Status::Ok => Span::styled("✔", Style::new().fg(MOSS).bold()),
        Status::Note => Span::styled("◆", Style::new().fg(GOLD)),
        Status::Problem => Span::styled("✖", Style::new().fg(BLOOD).bold()),
        Status::Off => Span::styled("○", Style::new().fg(SMOKE)),
    }
}

// ---- gear check -------------------------------------------------------------

fn checks_screen(frame: &mut Frame, app: &App, area: Rect) {
    let wide = area.width >= 100;
    let list_h = app.checks.len() as u16 + 4;
    let main_h = if wide { list_h } else { list_h + 8 };
    let [main, banner, tips] = Layout::vertical([
        Constraint::Length(main_h),
        Constraint::Length(4),
        Constraint::Min(0),
    ])
    .areas(area);
    let [list_area, about_area] = if wide {
        Layout::horizontal([Constraint::Percentage(58), Constraint::Percentage(42)])
            .spacing(1)
            .areas(main)
    } else {
        Layout::vertical([Constraint::Length(list_h), Constraint::Min(4)]).areas(main)
    };

    let inner_w = list_area.width.saturating_sub(2) as usize;
    let rows: Vec<Line> = app
        .checks
        .iter()
        .enumerate()
        .map(|(i, (id, outcome))| {
            let selected = i == app.check_sel;
            let title = format!("{:<26}", id.title());
            let room = inner_w.saturating_sub(title.chars().count() + 6);
            let detail = shorten(&outcome.detail, room);
            let pad = inner_w.saturating_sub(6 + title.chars().count() + detail.chars().count());
            let detail_color = match outcome.status {
                Status::Problem => BLOOD,
                Status::Note => GOLD,
                _ => ASH,
            };
            let mut line = Line::from(vec![
                Span::styled(if selected { " ▶ " } else { "   " }, Style::new().fg(EMBER)),
                status_icon(outcome.status, app.tick),
                "  ".into(),
                Span::styled(
                    title,
                    Style::new().fg(if selected { FLAME } else { PARCHMENT }),
                ),
                Span::styled(detail, Style::new().fg(detail_color)),
                " ".repeat(pad).into(),
            ]);
            if selected {
                line = line.style(Style::new().bg(SELECTED));
            }
            line
        })
        .collect();
    frame.render_widget(
        Paragraph::new(rows)
            .block(panel("Gear check", true).padding(ratatui::widgets::Padding::vertical(1))),
        list_area,
    );

    let (id, outcome) = &app.checks[app.check_sel];
    let mut about = vec![
        Line::from(vec![
            status_icon(outcome.status, app.tick),
            " ".into(),
            id.title().fg(FLAME).bold(),
        ]),
        Line::from(""),
        Line::from(id.about().fg(PARCHMENT)),
        Line::from(""),
        Line::from(outcome.detail.clone().fg(match outcome.status {
            Status::Problem => BLOOD,
            Status::Note => GOLD,
            Status::Ok => MOSS,
            _ => ASH,
        })),
    ];
    if let Some(fix) = &outcome.fix {
        about.push(Line::from(""));
        about.push(Line::from(theme::key("F", fix.label())));
    }
    frame.render_widget(
        Paragraph::new(about)
            .wrap(Wrap { trim: true })
            .block(panel("About this", false).padding(ratatui::widgets::Padding::horizontal(1))),
        about_area,
    );

    let (icon, headline, color, sub) = if let Some(fixing) = &app.fixing {
        (
            theme::spinner(app.tick),
            fixing.clone(),
            EMBER,
            "This can take a minute.".to_string(),
        )
    } else if app.checks.iter().any(|(_, o)| o.status == Status::Waiting) {
        (
            theme::spinner(app.tick),
            "Checking your gear…".into(),
            EMBER,
            String::new(),
        )
    } else if app.blocking_problems() > 0 {
        let n = app.blocking_problems();
        (
            "✖",
            format!(
                "{n} thing{} need{} attention before the adventure can begin",
                plural(n),
                if n == 1 { "s" } else { "" }
            ),
            BLOOD,
            "Select a red item with ↑ ↓ and press F to fix it. I re-check every few seconds."
                .into(),
        )
    } else {
        let notes = app.notes();
        let sub = if notes > 0 {
            format!(
                "{notes} optional tip{} above (◆), nothing that stops you.",
                plural(notes)
            )
        } else {
            "Everything looks perfect.".into()
        };
        (
            "✦",
            "All set! Press Enter to begin your adventure".into(),
            MOSS,
            sub,
        )
    };
    banner_box(frame, banner, icon, &headline, color, &sub, app);
    campfire_tip(frame, app, tips);
}

const TIPS: [&str; 6] = [
    "Characters remember what you tell them, and what they overhear.",
    "Rumours are leads: follow one and the story bends toward it.",
    "Talk about a place often enough and it may appear on the map.",
    "Say lets you speak; Act lets you do. Mix them freely.",
    "Your story saves itself after every turn. Quit whenever you like.",
    "Nobody waits for you: the vale keeps living between your turns.",
];

/// A rotating tip, shown when the window has room for it.
fn campfire_tip(frame: &mut Frame, app: &App, area: Rect) {
    if area.height < 5 {
        return;
    }
    let tip = TIPS[(app.tick as usize / 160) % TIPS.len()];
    let box_area = Rect {
        y: area.y + 1,
        height: 4,
        ..area
    };
    let text = vec![
        Line::from(vec![
            "✦ ".fg(EMBER),
            tip.fg(PARCHMENT).italic(),
            " ✦".fg(EMBER),
        ])
        .centered(),
    ];
    frame.render_widget(
        Paragraph::new(text)
            .block(panel("Campfire tip", false).padding(ratatui::widgets::Padding::top(1))),
        box_area,
    );
}

fn banner_box(
    frame: &mut Frame,
    area: Rect,
    icon: &str,
    headline: &str,
    color: Color,
    sub: &str,
    app: &App,
) {
    let sub_line = match &app.toast {
        Some(toast) => Line::from(toast.text.clone().fg(match toast.tone {
            Tone::Good => MOSS,
            Tone::Info => SKY,
            Tone::Bad => BLOOD,
        })),
        None => Line::from(sub.to_string().fg(ASH)),
    };
    let text = vec![
        Line::from(vec![
            Span::styled(format!("{icon}  "), Style::new().fg(color).bold()),
            headline.to_string().fg(color).bold(),
        ]),
        sub_line,
    ];
    frame.render_widget(
        Paragraph::new(text).alignment(Alignment::Center).block(
            Block::new()
                .borders(Borders::TOP)
                .border_style(Style::new().fg(BORDER))
                .padding(ratatui::widgets::Padding::top(1)),
        ),
        area,
    );
}

// ---- settings ----------------------------------------------------------------

fn settings_screen(frame: &mut Frame, app: &App, area: Rect) {
    let [list_area, about_area] =
        Layout::vertical([Constraint::Min(8), Constraint::Length(6)]).areas(area);
    let selected = Item::all()[app.setting_sel];
    let inner_w = list_area.width.saturating_sub(4) as usize;
    let mut rows = vec![];
    for (section, items) in SECTIONS {
        if !rows.is_empty() {
            rows.push(Line::from(""));
        }
        let rule = "─".repeat(inner_w.saturating_sub(section.len() + 6).min(60));
        rows.push(Line::from(vec![
            "  ".into(),
            section.to_uppercase().fg(GOLD).bold(),
            " ".into(),
            rule.fg(BORDER),
        ]));
        for item in items.iter() {
            rows.push(setting_row(app, *item, *item == selected, inner_w));
        }
    }
    // Keep the selected row visible on short windows.
    let row_of_selected = rows
        .iter()
        .position(|l| l.style.bg == Some(SELECTED))
        .unwrap_or(0) as u16;
    let visible = list_area.height.saturating_sub(2);
    let scroll = row_of_selected.saturating_sub(visible.saturating_sub(2));
    frame.render_widget(
        Paragraph::new(rows)
            .scroll((scroll, 0))
            .block(panel("Settings", true)),
        list_area,
    );

    let mut about = vec![
        Line::from(selected.label().fg(FLAME).bold()),
        Line::from(selected.about().fg(PARCHMENT)),
    ];
    if let Some(toast) = &app.toast {
        about.push(Line::from(toast.text.clone().fg(match toast.tone {
            Tone::Good => MOSS,
            Tone::Info => SKY,
            Tone::Bad => BLOOD,
        })));
    }
    frame.render_widget(
        Paragraph::new(about).wrap(Wrap { trim: true }).block(
            panel("What does this do?", false).padding(ratatui::widgets::Padding::horizontal(1)),
        ),
        about_area,
    );

    if app.editing.is_some() {
        edit_popup(frame, app, selected, area);
    }
}

fn setting_row(app: &App, item: Item, selected: bool, width: usize) -> Line<'static> {
    let label = format!("{:<30}", item.label());
    let value: Vec<Span<'static>> = match app.disabled(item) {
        Some(why) => vec![Span::styled(
            format!("— {why}"),
            Style::new().fg(SMOKE).italic(),
        )],
        None => setting_value(app, item, selected),
    };
    let used: usize = 5
        + label.chars().count()
        + value
            .iter()
            .map(|s| s.content.chars().count())
            .sum::<usize>();
    let mut spans = vec![
        Span::styled(
            if selected { "  ▶ " } else { "    " },
            Style::new().fg(EMBER),
        ),
        Span::styled(
            label,
            Style::new().fg(if selected { FLAME } else { PARCHMENT }),
        ),
    ];
    spans.extend(value);
    spans.push(" ".repeat(width.saturating_sub(used)).into());
    let line = Line::from(spans);
    if selected {
        line.style(Style::new().bg(SELECTED))
    } else {
        line
    }
}

fn toggle(on: bool, on_text: &str, off_text: &str) -> Vec<Span<'static>> {
    if on {
        vec![Span::styled(
            format!("● {on_text}"),
            Style::new().fg(MOSS).bold(),
        )]
    } else {
        vec![Span::styled(format!("○ {off_text}"), Style::new().fg(ASH))]
    }
}

fn setting_value(app: &App, item: Item, selected: bool) -> Vec<Span<'static>> {
    let arrows = |text: String| {
        let arrow = Style::new().fg(if selected { EMBER } else { SMOKE });
        vec![
            Span::styled("◀ ", arrow),
            Span::styled(text, Style::new().fg(GOLD).bold()),
            Span::styled(" ▶", arrow),
        ]
    };
    let teller = app.env.storyteller();
    match item {
        Item::Storyteller => arrows(teller.label().to_string()),
        Item::Key => match teller.key_name() {
            Some(name) if app.env.has_value(name) => vec![
                Span::styled("✔ saved", Style::new().fg(MOSS)),
                Span::styled("   Enter to replace", Style::new().fg(SMOKE)),
            ],
            _ => vec![
                Span::styled("✖ missing", Style::new().fg(BLOOD).bold()),
                Span::styled("   Enter to paste it", Style::new().fg(SMOKE)),
            ],
        },
        Item::Model => {
            let model = teller
                .model_name()
                .and_then(|k| app.env.get(k))
                .unwrap_or_else(|| "default".into());
            vec![
                Span::styled(model, Style::new().fg(GOLD)),
                Span::styled("   Enter to change", Style::new().fg(SMOKE)),
            ]
        }
        Item::FastTurns => toggle(
            app.env.get(config::FAST_TURNS).is_some_and(|v| v == "true"),
            "On",
            "Off",
        ),
        Item::SmartMemory => toggle(app.prefs.smart_memory, "On", "Off"),
        Item::PlaceSpotting => toggle(app.prefs.place_spotting, "On", "Off"),
        Item::GraphicsCard => toggle(app.prefs.graphics_card, "On (experimental)", "Off"),
        Item::Port => vec![
            Span::styled(
                app.prefs.game_port.to_string(),
                Style::new().fg(GOLD).bold(),
            ),
            Span::styled(
                format!("   localhost:{}", app.prefs.game_port),
                Style::new().fg(SMOKE),
            ),
        ],
        Item::OpenBrowser => toggle(app.prefs.open_browser, "Yes", "No"),
        Item::Rebuild => toggle(app.prefs.rebuild, "Yes (slower start)", "No"),
        Item::StopOnQuit => {
            if app.prefs.stop_on_quit {
                arrows("Stop everything".into())
            } else {
                arrows("Keep the server warm".into())
            }
        }
    }
}

fn edit_popup(frame: &mut Frame, app: &App, item: Item, area: Rect) {
    let width = area.width.min(70);
    let popup = Rect {
        x: area.x + (area.width - width) / 2,
        y: area.y + area.height.saturating_sub(9) / 2,
        width,
        height: 9.min(area.height),
    };
    let buffer = app.editing.clone().unwrap_or_default();
    let secret = item == Item::Key;
    let shown = if secret {
        "•".repeat(buffer.chars().count().min(48))
    } else {
        buffer
    };
    let cursor = if (app.tick / 6).is_multiple_of(2) {
        "▌"
    } else {
        " "
    };
    let hint = match item {
        Item::Key => "Paste your key (right-click or Ctrl+V). It's saved only on this PC.",
        Item::Port => "Type a number, for example 5180.",
        _ => "Type the model name exactly as the AI service lists it.",
    };
    let teller = app.env.storyteller();
    let title = match (item, teller) {
        (Item::Key, Storyteller::OpenRouter) => "OpenRouter key",
        (Item::Key, _) => "Venice key",
        _ => item.label(),
    };
    let text = vec![
        Line::from(hint.fg(ASH)),
        Line::from(""),
        Line::from(vec![
            " › ".fg(EMBER).bold(),
            shown.fg(PARCHMENT),
            cursor.fg(EMBER),
        ])
        .style(Style::new().bg(SELECTED)),
        Line::from(""),
        Line::from([theme::key("Enter", "save"), theme::key("Esc", "cancel")].concat()),
    ];
    frame.render_widget(Clear, popup);
    frame.render_widget(
        Paragraph::new(text)
            .wrap(Wrap { trim: false })
            .block(panel(title, true).padding(ratatui::widgets::Padding::new(2, 2, 1, 0))),
        popup,
    );
}

// ---- launching and playing ---------------------------------------------------

fn step_icon(state: StepState, tick: u64) -> Span<'static> {
    match state {
        StepState::Waiting => Span::styled("·", Style::new().fg(SMOKE)),
        StepState::Running => Span::styled(theme::spinner(tick), Style::new().fg(EMBER).bold()),
        StepState::Done => Span::styled("✔", Style::new().fg(MOSS).bold()),
        StepState::Skipped => Span::styled("–", Style::new().fg(ASH)),
        StepState::Failed => Span::styled("✖", Style::new().fg(BLOOD).bold()),
    }
}

fn launch_screen(frame: &mut Frame, app: &App, area: Rect) {
    if app.log_full {
        return logs(frame, app, area);
    }
    let steps_h = app.steps.len() as u16 + 7;
    let [steps_area, log_area] =
        Layout::vertical([Constraint::Length(steps_h), Constraint::Min(3)]).areas(area);
    let inner = steps_area.inner(Margin::new(2, 1));
    let mut lines = vec![Line::from("")];
    for (step, state, detail) in &app.steps {
        let title_color = match state {
            StepState::Waiting => SMOKE,
            StepState::Running => FLAME,
            StepState::Failed => BLOOD,
            _ => PARCHMENT,
        };
        lines.push(Line::from(vec![
            "  ".into(),
            step_icon(*state, app.tick),
            "  ".into(),
            Span::styled(
                format!("{:<42}", step.title()),
                Style::new().fg(title_color),
            ),
            Span::styled(detail.clone(), Style::new().fg(ASH)),
        ]));
    }
    let finished = app
        .steps
        .iter()
        .filter(|(_, s, _)| matches!(s, StepState::Done | StepState::Skipped))
        .count();
    let running = app.steps.iter().any(|(_, s, _)| *s == StepState::Running) as usize as f64 * 0.5;
    let ratio = (finished as f64 + running) / app.steps.len().max(1) as f64;
    lines.push(Line::from(""));
    lines.push(theme::bar(inner.width.saturating_sub(10), ratio, app.tick).centered());
    match &app.launch_error {
        Some(why) => {
            lines.push(Line::from(vec!["✖ ".fg(BLOOD).bold(), why.clone().fg(BLOOD)]).centered())
        }
        None => lines.push(Line::from(format!("{:.0}%", ratio * 100.0).fg(GOLD)).centered()),
    }
    let hot = app.launch_error.is_none();
    frame.render_widget(
        Paragraph::new(lines).block(panel("Lighting the hearth", hot)),
        steps_area,
    );
    logs(frame, app, log_area);
}

fn playing_screen(frame: &mut Frame, app: &App, area: Rect) {
    if app.log_full {
        return logs(frame, app, area);
    }
    let [hero, cards, log_area] = Layout::vertical([
        Constraint::Length(7),
        Constraint::Length(5),
        Constraint::Min(3),
    ])
    .areas(area);
    let url = app.plan.as_ref().map(|p| p.game_url()).unwrap_or_default();
    let glow = if (app.tick / 8).is_multiple_of(2) {
        FLAME
    } else {
        EMBER
    };
    let hero_text = vec![
        Line::from(""),
        Line::from("✦  Your adventure awaits  ✦".fg(glow).bold()).centered(),
        Line::from(""),
        Line::from(vec![
            "Play at  ".fg(ASH),
            url.fg(SKY).bold().underlined(),
            "   (press O to open it)".fg(ASH),
        ])
        .centered(),
        Line::from(
            "Keep this window open while you play; quitting here ends the session."
                .fg(SMOKE)
                .italic(),
        )
        .centered(),
    ];
    frame.render_widget(Paragraph::new(hero_text).block(panel("Ready", true)), hero);

    let health = app.health;
    let memory_state = match health.memory {
        None => (None, "off"),
        Some(true) => (Some(true), "awake"),
        Some(false) => (Some(false), "not running"),
    };
    let entries = [
        (
            "Save database",
            Some(health.database),
            if health.database {
                "awake"
            } else {
                "not answering"
            },
        ),
        (
            "Game server",
            Some(health.server),
            if health.server {
                "awake"
            } else {
                "not answering"
            },
        ),
        ("Smart memory", memory_state.0, memory_state.1),
        (
            "Game screen",
            Some(health.screen),
            if health.screen {
                "awake"
            } else if app.owns(Source::Screen) {
                "stopped"
            } else {
                "not running"
            },
        ),
    ];
    let columns = Layout::horizontal([Constraint::Ratio(1, 4); 4])
        .spacing(1)
        .split(cards);
    for ((name, up, words), col) in entries.into_iter().zip(columns.iter()) {
        let (dot, color) = match up {
            Some(true) => (
                if (app.tick / 10).is_multiple_of(2) {
                    "●"
                } else {
                    "◉"
                },
                MOSS,
            ),
            Some(false) => ("●", BLOOD),
            None => ("○", SMOKE),
        };
        let text =
            vec![Line::from(vec![dot.fg(color).bold(), "  ".into(), words.fg(color)]).centered()];
        frame.render_widget(
            Paragraph::new(text)
                .block(panel(name, false).padding(ratatui::widgets::Padding::top(1))),
            *col,
        );
    }
    logs(frame, app, log_area);
}

// ---- backups -----------------------------------------------------------------

fn backups_screen(frame: &mut Frame, app: &App, area: Rect) {
    if app.log_full {
        return logs(frame, app, area);
    }
    let rows = match &app.backups {
        Some(Ok(list)) => list.len().max(1) as u16,
        _ => 1,
    };
    let [list_area, status_area, log_area] = Layout::vertical([
        Constraint::Length((rows + 5).min(14)),
        Constraint::Length(5),
        Constraint::Min(3),
    ])
    .areas(area);

    let inner_w = list_area.width.saturating_sub(2) as usize;
    let mut lines = vec![Line::from(vec![
        "     ".into(),
        format!("{:<24}{:<16}{}", "Taken", "Stories", "Size")
            .fg(GOLD)
            .bold(),
    ])];
    match &app.backups {
        None => lines.push(Line::from(vec![
            "   ".into(),
            theme::spinner(app.tick).fg(EMBER),
            "  Looking for your backups…".fg(ASH),
        ])),
        Some(Err(why)) => lines.push(Line::from(vec![
            "   ".into(),
            "✖  ".fg(BLOOD).bold(),
            why.clone().fg(BLOOD),
        ])),
        Some(Ok(list)) if list.is_empty() => lines.push(Line::from(
            "   No backups yet. Press N to make the first one.".fg(ASH),
        )),
        Some(Ok(list)) => {
            for (i, backup) in list.iter().enumerate() {
                let selected = i == app.backup_sel;
                let text = format!(
                    "{:<24}{:<16}{:<10}",
                    backup.when(),
                    backups::stories_label(backup.stories),
                    backups::size_label(&backup.size),
                );
                let tag = if i == 0 { "newest" } else { "" };
                let used = 5 + text.chars().count() + tag.chars().count();
                let mut line = Line::from(vec![
                    Span::styled(if selected { " ▶ " } else { "   " }, Style::new().fg(EMBER)),
                    "  ".into(),
                    Span::styled(
                        text,
                        Style::new().fg(if selected { FLAME } else { PARCHMENT }),
                    ),
                    Span::styled(tag, Style::new().fg(SMOKE).italic()),
                    " ".repeat(inner_w.saturating_sub(used)).into(),
                ]);
                if selected {
                    line = line.style(Style::new().bg(SELECTED));
                }
                lines.push(line);
            }
        }
    }
    frame.render_widget(
        Paragraph::new(lines)
            .block(panel("Backups", true).padding(ratatui::widgets::Padding::vertical(1))),
        list_area,
    );

    let (icon, headline, color, sub) = if let Some(busy) = &app.backup_busy {
        (
            theme::spinner(app.tick),
            busy.clone(),
            EMBER,
            "This can take a few minutes. Each step shows in the log below.",
        )
    } else {
        match &app.backup_note {
            Some((Tone::Bad, text)) => ("✖", text.clone(), BLOOD, "The log below has the details."),
            Some((_, text)) => ("✔", text.clone(), MOSS, ""),
            None => (
                "✦",
                "Your game is backed up every day, and the newest 7 backups are kept.".into(),
                GOLD,
                "Choose one and press Enter to put it back, or N to back up now.",
            ),
        }
    };
    let sub_line = match &app.toast {
        Some(toast) => Line::from(toast.text.clone().fg(match toast.tone {
            Tone::Good => MOSS,
            Tone::Info => SKY,
            Tone::Bad => BLOOD,
        })),
        None => Line::from(sub.fg(ASH)),
    };
    let text = vec![
        Line::from(vec![
            Span::styled(format!("{icon}  "), Style::new().fg(color).bold()),
            headline.fg(color).bold(),
        ]),
        sub_line,
    ];
    frame.render_widget(
        Paragraph::new(text)
            .alignment(Alignment::Center)
            .wrap(Wrap { trim: true }),
        status_area.inner(Margin::new(1, 1)),
    );
    logs(frame, app, log_area);

    if app.confirm_restore
        && let Some(backup) = app.chosen_backup()
    {
        confirm_popup(frame, backup, area);
    }
}

fn confirm_popup(frame: &mut Frame, backup: &Backup, area: Rect) {
    let width = area.width.min(76);
    let height = 14.min(area.height);
    let popup = Rect {
        x: area.x + (area.width - width) / 2,
        y: area.y + area.height.saturating_sub(height) / 2,
        width,
        height,
    };
    let text = vec![
        Line::from(backup.summary().fg(GOLD).bold()),
        Line::from(""),
        Line::from(
            "Your game goes back to how it was then. Everything since is replaced: \
             stories, characters, worlds and pictures."
                .fg(PARCHMENT),
        ),
        Line::from(""),
        Line::from(
            "Your game as it is now is backed up first, so you can undo this here.".fg(MOSS),
        ),
        Line::from("The game server stops for a minute or two and starts again by itself.".fg(ASH)),
        Line::from(""),
        Line::from(
            [
                theme::key("Y", "yes, put it back"),
                theme::key("Esc", "no, keep my game as it is"),
            ]
            .concat(),
        ),
    ];
    frame.render_widget(Clear, popup);
    frame.render_widget(
        Paragraph::new(text).wrap(Wrap { trim: true }).block(
            panel("Put this backup back?", true)
                .padding(ratatui::widgets::Padding::new(2, 2, 1, 0)),
        ),
        popup,
    );
}

fn closing_screen(frame: &mut Frame, app: &App, area: Rect) {
    let [message, log_area] =
        Layout::vertical([Constraint::Length(7), Constraint::Min(3)]).areas(area);
    let what = if app.prefs.stop_on_quit {
        "Stopping the game and its server…"
    } else {
        "Closing the game screen; the server stays warm…"
    };
    let text = vec![
        Line::from(""),
        Line::from(vec![
            theme::spinner(app.tick).fg(EMBER).bold(),
            "  ".into(),
            what.fg(FLAME).bold(),
        ])
        .centered(),
        Line::from(""),
        Line::from(
            "Your story is saved. See you by the fire, traveller."
                .fg(GOLD)
                .italic(),
        )
        .centered(),
    ];
    frame.render_widget(Paragraph::new(text).block(panel("Farewell", true)), message);
    logs(frame, app, log_area);
}

fn logs(frame: &mut Frame, app: &App, area: Rect) {
    let tabs = [
        (None, "all"),
        (Some(Source::Server), "server"),
        (Some(Source::Memory), "memory"),
        (Some(Source::Screen), "screen"),
        (Some(Source::Backups), "backups"),
        (Some(Source::Launcher), "launcher"),
    ];
    let mut title = vec![
        " ".into(),
        "Behind the scenes".fg(FLAME).bold(),
        "  ".into(),
    ];
    for (filter, name) in tabs {
        if filter == app.log_filter {
            title.push(Span::styled(
                format!(" {name} "),
                Style::new().fg(BG).bg(EMBER).bold(),
            ));
        } else {
            title.push(Span::styled(format!(" {name} "), Style::new().fg(SMOKE)));
        }
    }
    title.push(" ".into());
    let block = Block::new()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::new().fg(BORDER))
        .title(Line::from(title))
        .style(Style::new().bg(PANEL));
    let height = area.height.saturating_sub(2) as usize;
    let lines = app.visible_logs();
    let end = lines.len().saturating_sub(app.log_scroll.min(lines.len()));
    let start = end.saturating_sub(height);
    let width = area.width.saturating_sub(14) as usize;
    let rendered: Vec<Line> = lines[start..end]
        .iter()
        .map(|(source, text)| {
            let color = match source {
                Source::Launcher => GOLD,
                Source::Server => SKY,
                Source::Memory => MOSS,
                Source::Screen => EMBER,
                Source::Backups => PARCHMENT,
            };
            Line::from(vec![
                Span::styled(format!("{:>8} │ ", source.label()), Style::new().fg(color)),
                Span::styled(shorten(text, width), Style::new().fg(ASH)),
            ])
        })
        .collect();
    let rendered = if rendered.is_empty() {
        vec![Line::from("Nothing here yet.".fg(SMOKE).italic())]
    } else {
        rendered
    };
    frame.render_widget(Paragraph::new(rendered).block(block), area);
}

// ---- footer ------------------------------------------------------------------

fn footer(frame: &mut Frame, app: &App, area: Rect) {
    let mut spans: Vec<Span> = vec!["  ".into()];
    let keys: Vec<(&str, &str)> = if app.editing.is_some() {
        vec![("Enter", "save"), ("Esc", "cancel")]
    } else if app.confirm_restore {
        vec![
            ("Y", "yes, put it back"),
            ("Esc", "no, keep my game as it is"),
        ]
    } else {
        match app.screen {
            Screen::Checks => vec![
                ("Enter", "Start adventure"),
                ("F", "fix it"),
                ("S", "Settings"),
                ("Q", "quit"),
                ("R", "check again"),
                ("↑↓", "choose"),
            ],
            Screen::Settings => vec![
                ("↑↓", "choose"),
                ("←→", "change"),
                ("Enter", "edit"),
                ("Esc", "back"),
                ("Q", "quit"),
            ],
            Screen::Launch if app.launch_error.is_some() => {
                vec![
                    ("R", "try again"),
                    ("B", "back to checks"),
                    ("L", "big log"),
                    ("Tab", "filter log"),
                    ("Q", "quit"),
                ]
            }
            Screen::Launch => vec![
                ("L", "big log"),
                ("Tab", "filter log"),
                ("↑↓", "scroll"),
                ("Q", "cancel & quit"),
            ],
            Screen::Playing => {
                let quit = if app.prefs.stop_on_quit {
                    "quit & stop"
                } else {
                    "quit"
                };
                vec![
                    ("O", "open game"),
                    ("R", "restart"),
                    ("B", "backups"),
                    ("L", "big log"),
                    ("Tab", "filter log"),
                    ("Q", quit),
                ]
            }
            Screen::Backups if app.backup_busy.is_some() => {
                vec![("L", "big log"), ("Tab", "filter log"), ("↑↓", "choose")]
            }
            Screen::Backups => vec![
                ("Enter", "put this one back"),
                ("N", "back up now"),
                ("Esc", "back"),
                ("R", "look again"),
                ("↑↓", "choose"),
                ("L", "big log"),
                ("Q", "quit"),
            ],
            Screen::Closing => vec![],
        }
    };
    // Keys come most important first; any that don't fit are left out.
    let mut used = 2;
    for (cap, action) in keys {
        let width = cap.chars().count() + action.chars().count() + 6;
        if used + width <= area.width as usize {
            spans.extend(theme::key(cap, action));
            used += width;
        }
    }
    let [rule, line] = Layout::vertical([Constraint::Length(1), Constraint::Length(1)]).areas(area);
    let _ = rule;
    frame.render_widget(Paragraph::new(Line::from(spans)), line);
}

// ---- helpers -----------------------------------------------------------------

fn plural(n: usize) -> &'static str {
    if n == 1 { "" } else { "s" }
}

fn shorten(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        return text.to_string();
    }
    let mut out: String = text.chars().take(max.saturating_sub(1)).collect();
    out.push('…');
    out
}

#[cfg(test)]
mod snapshots {
    //! `SNAPSHOT_DIR=… cargo test snapshots -- --ignored` renders each screen
    //! to a coloured HTML page, for checking the look without a terminal.

    use std::fmt::Write as _;
    use std::time::{Duration, Instant};

    use ratatui::Terminal;
    use ratatui::backend::TestBackend;
    use ratatui::buffer::Buffer;
    use ratatui::style::{Color, Modifier};

    use super::*;
    use crate::services::{Health, Step};

    fn css(color: Color, fallback: &str) -> String {
        match color {
            Color::Rgb(r, g, b) => format!("rgb({r},{g},{b})"),
            _ => fallback.to_string(),
        }
    }

    fn html(buf: &Buffer) -> String {
        let mut out = String::from(
            "<html><head><meta charset=\"utf-8\"></head><body style=\"background:#111;margin:0\"><pre style=\"font:13px/1.2 'Cascadia Mono',Consolas,monospace;margin:8px\">",
        );
        for y in 0..buf.area.height {
            for x in 0..buf.area.width {
                let cell = &buf[(x, y)];
                let weight = if cell.modifier.contains(Modifier::BOLD) {
                    "bold"
                } else {
                    "normal"
                };
                let style = if cell.modifier.contains(Modifier::ITALIC) {
                    "italic"
                } else {
                    "normal"
                };
                let text = cell.symbol().replace('&', "&amp;").replace('<', "&lt;");
                let _ = write!(
                    out,
                    "<span style=\"color:{};background:{};font-weight:{weight};font-style:{style}\">{text}</span>",
                    css(cell.fg, "#eee"),
                    css(cell.bg, "#161010"),
                );
            }
            out.push('\n');
        }
        out + "</pre></body></html>"
    }

    #[test]
    #[ignore]
    fn snapshots() {
        let dir = std::path::PathBuf::from(std::env::var("SNAPSHOT_DIR").expect("SNAPSHOT_DIR"));
        let root = crate::sys::find_root().expect("run inside the repo");
        let mut app = App::new(root);
        let started = Instant::now();
        while app.checking && started.elapsed() < Duration::from_secs(60) {
            app.update(Rect::new(0, 0, 120, HEADER_H));
            std::thread::sleep(Duration::from_millis(50));
        }
        for _ in 0..60 {
            app.update(Rect::new(0, 0, 120, HEADER_H));
        }
        let shoot = |app: &App, name: &str, w: u16, h: u16| {
            let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
            terminal.draw(|f| draw(f, app)).unwrap();
            std::fs::write(
                dir.join(format!("{name}.html")),
                html(terminal.backend().buffer()),
            )
            .unwrap();
        };
        shoot(&app, "1-checks", 120, 36);
        shoot(&app, "1b-checks-narrow", 80, 32);
        app.check_sel = 5;
        shoot(&app, "1c-checks-storyteller", 120, 36);
        app.screen = Screen::Settings;
        app.setting_sel = 1;
        shoot(&app, "2-settings", 120, 36);
        app.editing = Some("sk-or-v1-abc".into());
        shoot(&app, "2b-settings-edit", 120, 36);
        app.editing = None;
        app.screen = Screen::Launch;
        app.steps = vec![
            (Step::Server, StepState::Done, String::new()),
            (Step::Answer, StepState::Done, "answered after 9s".into()),
            (
                Step::Memory,
                StepState::Running,
                "loading the models… 4s".into(),
            ),
            (Step::Screen, StepState::Waiting, String::new()),
            (Step::Browser, StepState::Waiting, String::new()),
        ];
        for line in [
            " Container ember-vale-db-1  Running",
            " Container ember-vale-api-1  Started",
        ] {
            app.logs.push_back((Source::Server, line.into()));
        }
        app.logs
            .push_back((Source::Memory, "INFO embedder ready on ['CPU']".into()));
        shoot(&app, "3-launch", 120, 36);
        app.screen = Screen::Playing;
        app.plan = Some(crate::services::Plan {
            root: app.root.clone(),
            prefs: app.prefs.clone(),
            api_port: 8101,
            db_port: 5433,
            cancel: Default::default(),
        });
        app.health = Health {
            database: true,
            server: true,
            memory: Some(true),
            screen: true,
        };
        app.logs
            .push_back((Source::Screen, "VITE v5.4 ready in 412 ms".into()));
        shoot(&app, "4-playing", 120, 36);
        app.screen = Screen::Backups;
        app.backups = Some(Ok(crate::app::tests::two_backups()));
        shoot(&app, "4b-backups", 120, 36);
        app.confirm_restore = true;
        shoot(&app, "4c-backups-restore", 120, 36);
        app.confirm_restore = false;
        app.screen = Screen::Closing;
        shoot(&app, "5-closing", 120, 36);
        shoot(&app, "6-too-small", 50, 16);
    }
}

#[cfg(test)]
mod backups_render {
    use ratatui::Terminal;
    use ratatui::backend::TestBackend;

    use super::*;
    use crate::app::tests::{quiet_app, two_backups};

    fn screen_text(app: &App, w: u16, h: u16) -> String {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
        terminal.draw(|f| draw(f, app)).unwrap();
        let buf = terminal.backend().buffer();
        (0..buf.area.height)
            .map(|y| {
                (0..buf.area.width)
                    .map(|x| buf[(x, y)].symbol())
                    .collect::<String>()
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    #[test]
    fn the_playing_footer_offers_backups() {
        let mut app = quiet_app();
        app.screen = Screen::Playing;
        assert!(screen_text(&app, 120, 36).contains(" B  backups"));
    }

    #[test]
    fn backups_are_listed_in_plain_words() {
        let mut app = quiet_app();
        app.screen = Screen::Backups;
        app.backups = Some(Ok(two_backups()));
        let text = screen_text(&app, 120, 36);
        let newest = &two_backups()[0];
        assert!(text.contains(&newest.when()), "{text}");
        for words in [
            "3 stories",
            "1.9 MB",
            "1 story",
            "812 KB",
            "newest",
            "backed up every day",
            "Enter  put this one back",
            "N  back up now",
        ] {
            assert!(text.contains(words), "missing {words:?} in\n{text}");
        }
        assert!(!text.contains("20261009"), "no raw stamps on screen");
    }

    #[test]
    fn the_restore_question_says_what_is_replaced() {
        let mut app = quiet_app();
        app.screen = Screen::Backups;
        app.backups = Some(Ok(two_backups()));
        app.confirm_restore = true;
        let text = screen_text(&app, 120, 36);
        for words in [
            "Put this backup back?",
            "Everything since is replaced",
            "backed up first",
            "starts again by itself",
            "Y  yes, put it back",
        ] {
            assert!(text.contains(words), "missing {words:?} in\n{text}");
        }
    }

    #[test]
    fn failures_and_progress_are_said_plainly() {
        let mut app = quiet_app();
        app.screen = Screen::Backups;
        app.backups = Some(Err("Docker Desktop isn't running.".into()));
        assert!(screen_text(&app, 120, 36).contains("Docker Desktop isn't running."));
        app.backups = Some(Ok(vec![]));
        assert!(screen_text(&app, 120, 36).contains("No backups yet"));
        app.backup_busy = Some("Step 3 of 4: Putting back the backup…".into());
        assert!(screen_text(&app, 120, 36).contains("Step 3 of 4: Putting back"));
        app.backup_busy = None;
        app.backup_note = Some((Tone::Bad, "Step 1 of 4 failed. Nothing was changed.".into()));
        assert!(screen_text(&app, 120, 36).contains("Nothing was changed."));
    }
}
