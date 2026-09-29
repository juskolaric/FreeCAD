/***************************************************************************
 *   Copyright (c) 2026 Jus Kolaric                                        *
 *                                                                         *
 *   This file is part of FreeCAD (lastna kopija juskolaric/FreeCAD).      *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/

#include "PreCompiled.h"
#ifndef _PreComp_
#include <QAction>
#include <QActionEvent>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QMenu>
#include <QResizeEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QTimer>
#include <QToolBar>
#include <QVBoxLayout>
#include <QWidgetAction>
#endif

#include <App/Application.h>
#include <Base/Parameter.h>

#include "RibbonBar.h"
#include "Action.h"
#include "Application.h"
#include "Command.h"
#include "MainWindow.h"
#include "ToolBarManager.h"
#include "WorkbenchSelector.h"


using namespace Gui;

namespace
{

ParameterGrp::handle ribbonParams()
{
    return App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/RibbonBar"
    );
}

// Napis brez koncnih pik. Dolg napis velikega gumba se prelomi v dve vrstici na presledku,
// ki je najblizje sredini (kot v SolidWorksu: "Extruded" / "Boss/Base").
QString ribbonLabel(const QString& text, bool wrap)
{
    QString label = text.trimmed();
    while (label.endsWith(QLatin1String("...")) || label.endsWith(QChar(0x2026))) {
        label.chop(label.endsWith(QChar(0x2026)) ? 1 : 3);
        label = label.trimmed();
    }
    if (!wrap || label.length() <= 9) {
        return label;
    }
    const int mid = label.length() / 2;
    int best = -1;
    for (int i = 0; i < label.length(); ++i) {
        if (label.at(i) == QLatin1Char(' ') && (best < 0 || qAbs(i - mid) < qAbs(best - mid))) {
            best = i;
        }
    }
    if (best > 0) {
        label[best] = QLatin1Char('\n');
    }
    return label;
}

}  // namespace

// ---------------------------------------------------------------------------
// RibbonButton

RibbonButton::RibbonButton(QAction* action, RibbonButtonStyle style, int iconSize, QWidget* parent)
    : QToolButton(parent)
    , style(style)
{
    setAutoRaise(true);
    setFocusPolicy(Qt::NoFocus);
    setIconSize(QSize(iconSize, iconSize));
    switch (style) {
        case RibbonButtonStyle::Large:
            setToolButtonStyle(Qt::ToolButtonTextUnderIcon);
            break;
        case RibbonButtonStyle::Small:
            setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
            break;
        case RibbonButtonStyle::Icon:
            setToolButtonStyle(Qt::ToolButtonIconOnly);
            break;
    }
    setDefaultAction(action);
    applyText();
}

void RibbonButton::actionEvent(QActionEvent* event)
{
    // QToolButton ob spremembi dejanja znova prepise napis, zato ga postavimo se enkrat.
    QToolButton::actionEvent(event);
    if (event->type() == QEvent::ActionChanged) {
        applyText();
    }
}

void RibbonButton::applyText()
{
    if (style == RibbonButtonStyle::Icon) {
        return;
    }
    if (QAction* action = defaultAction()) {
        setText(ribbonLabel(action->iconText(), style == RibbonButtonStyle::Large));
    }
}

// ---------------------------------------------------------------------------
// RibbonBar

RibbonBar* RibbonBar::_instance = nullptr;  // NOLINT

bool RibbonBar::isEnabled()
{
    static const bool enabled = ribbonParams()->GetBool("Enabled", true);
    return enabled;
}

bool RibbonBar::isGlobalToolBar(const QString& name)
{
    static const QSet<QString> global = {
        QStringLiteral("File"),
        QStringLiteral("Edit"),
        QStringLiteral("Clipboard"),
        QStringLiteral("Macro"),
        QStringLiteral("View"),
        QStringLiteral("Individual Views"),
        QStringLiteral("Structure"),
        QStringLiteral("Help"),
    };
    return global.contains(name);
}

RibbonBar* RibbonBar::instance()
{
    return _instance;
}

RibbonBar* RibbonBar::create(QWidget* parent)
{
    if (!_instance) {
        _instance = new RibbonBar(parent);
    }
    return _instance;
}

RibbonBar::RibbonBar(QWidget* parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("RibbonBar"));

    ParameterGrp::handle params = ribbonParams();
    largeIcon = int(params->GetInt("LargeIconSize", 32));
    smallIcon = int(params->GetInt("SmallIconSize", 16));
    compactIcon = int(params->GetInt("CompactIconSize", 24));
    defaultLargeCount = int(params->GetInt("DefaultLargeCount", 2));

    vbox = new QVBoxLayout(this);
    vbox->setContentsMargins(0, 0, 0, 0);
    vbox->setSpacing(0);

    tabRow = new QWidget(this);
    tabRow->setObjectName(QStringLiteral("RibbonTabRow"));
    tabLayout = new QHBoxLayout(tabRow);
    tabLayout->setContentsMargins(4, 0, 4, 0);
    tabLayout->setSpacing(0);
    vbox->addWidget(tabRow);

    scroll = new QScrollArea(this);
    scroll->setObjectName(QStringLiteral("RibbonPanelScroll"));
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setWidgetResizable(true);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    panel = new QWidget();
    panel->setObjectName(QStringLiteral("RibbonPanel"));
    panelLayout = new QHBoxLayout(panel);
    panelLayout->setContentsMargins(4, 2, 4, 2);
    panelLayout->setSpacing(3);
    panelLayout->addStretch(1);
    scroll->setWidget(panel);
    vbox->addWidget(scroll);

    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void RibbonBar::ensureTabBar()
{
    if (tabWidget) {
        return;
    }
    Command* cmd = Application::Instance->commandManager().getCommandByName("Std_Workbench");
    if (!cmd) {
        return;
    }
    auto group = qobject_cast<WorkbenchGroup*>(cmd->getAction());
    if (!group) {
        return;
    }
    auto tabs = new WorkbenchTabWidget(group, tabRow);
    tabLayout->addWidget(tabs);
    tabLayout->addStretch(1);
    tabWidget = tabs;
}

int RibbonBar::largeCountFor(const QString& toolbarName) const
{
    ParameterGrp::handle grp = ribbonParams()->GetGroup("LargeCount");
    return int(grp->GetInt(toolbarName.toUtf8().constData(), defaultLargeCount));
}

bool RibbonBar::isToolBarShown(QToolBar* toolbar) const
{
    const QString name = toolbar->objectName();
    if (forcedHidden.contains(name)) {
        return false;
    }
    if (forcedShown.contains(name)) {
        return true;
    }

    QVariant property = toolbar->toggleViewAction()->property("DefaultVisibility");
    auto policy = property.isNull()
        ? ToolBarItem::DefaultVisibility::Visible
        : static_cast<ToolBarItem::DefaultVisibility>(property.toInt());

    // Uporabnikova izbira vidnosti (kontekstni meni orodnih vrstic) velja tudi tukaj.
    ParameterGrp::handle hPref
        = App::GetApplication().GetUserParameter().GetGroup("BaseApp/MainWindow/Toolbars");
    switch (policy) {
        case ToolBarItem::DefaultVisibility::Visible:
            return hPref->GetBool(name.toUtf8().constData(), true);
        case ToolBarItem::DefaultVisibility::Hidden:
            return hPref->GetBool(name.toUtf8().constData(), false);
        case ToolBarItem::DefaultVisibility::Unavailable:
            return false;
    }
    return true;
}

QWidget* RibbonBar::buildGroup(
    const QList<QAction*>& actions,
    QToolBar* source,
    int largeCount,
    bool compact
)
{
    auto group = new QWidget(panel);
    group->setToolTip(source->windowTitle());
    auto grid = new QGridLayout(group);
    grid->setContentsMargins(2, 0, 2, 0);
    grid->setHorizontalSpacing(1);
    grid->setVerticalSpacing(0);

    int column = 0;
    int row = 0;
    int index = 0;
    for (QAction* action : actions) {
        const bool large = index < largeCount;
        RibbonButtonStyle style = RibbonButtonStyle::Small;
        int iconSize = smallIcon;
        if (large) {
            style = RibbonButtonStyle::Large;
            iconSize = largeIcon;
        }
        else if (compact) {
            style = RibbonButtonStyle::Icon;
            iconSize = compactIcon;
        }
        auto button = new RibbonButton(action, style, iconSize, group);

        // Spustni meniji (skupine ukazov) so na gumbu klasicne orodne vrstice; delimo si jih.
        if (auto sourceButton = qobject_cast<QToolButton*>(source->widgetForAction(action))) {
            if (sourceButton->menu()) {
                button->setMenu(sourceButton->menu());
                button->setPopupMode(sourceButton->popupMode());
            }
        }

        if (large) {
            if (row > 0) {
                row = 0;
                ++column;
            }
            grid->addWidget(button, 0, column, 3, 1);
            ++column;
        }
        else {
            grid->addWidget(button, row, column, 1, 1, Qt::AlignLeft | Qt::AlignVCenter);
            ++row;
            if (row == 3) {
                row = 0;
                ++column;
            }
        }
        button->show();
        ++index;
    }
    for (int r = 0; r < 3; ++r) {
        grid->setRowStretch(r, 1);
    }
    return group;
}

void RibbonBar::build(bool compact)
{
    compactMode = compact;

    // Izprazni plosco.
    while (QLayoutItem* item = panelLayout->takeAt(0)) {
        if (QWidget* widget = item->widget()) {
            widget->hide();
            widget->deleteLater();
        }
        delete item;
    }

    MainWindow* mw = getMainWindow();
    bool first = true;
    for (const QString& name : currentNames) {
        if (isGlobalToolBar(name)) {
            continue;
        }
        auto toolbar = mw->findChild<Gui::ToolBar*>(name);
        if (!toolbar || !isToolBarShown(toolbar)) {
            continue;
        }

        // V zgoscenem nacinu je velik le prvi gumb skupine.
        const int largeCount = compact ? qMin(1, largeCountFor(name)) : largeCountFor(name);

        QList<QAction*> group;
        auto flush = [&]() {
            if (group.isEmpty()) {
                return;
            }
            if (!first) {
                // Tanka navpicna crta med skupinami (kot v SolidWorksu).
                auto line = new QWidget(panel);
                line->setObjectName(QStringLiteral("RibbonSeparator"));
                line->setFixedWidth(1);
                line->setStyleSheet(QStringLiteral("background-color: palette(mid);"));
                panelLayout->addWidget(line);
                line->show();
            }
            first = false;
            QWidget* groupWidget = buildGroup(group, toolbar, largeCount, compact);
            panelLayout->addWidget(groupWidget);
            groupWidget->show();  // takoj, da je velikost plosce znana ze pred obhodom dogodkov
            group.clear();
        };

        for (QAction* action : toolbar->actions()) {
            if (action->isSeparator()) {
                flush();
                continue;
            }
            if (qobject_cast<QWidgetAction*>(action) || !action->isVisible()) {
                continue;  // gradniki v orodnih vrsticah (izbirniki) v tej razlicici niso podprti
            }
            group.append(action);
        }
        flush();
    }
    panelLayout->addStretch(1);

    if (!compact) {
        normalWidth = panelWidth();
    }
}

int RibbonBar::panelWidth()
{
    panelLayout->activate();
    return panel->sizeHint().width();
}

void RibbonBar::fitToWidth()
{
    const int available = scroll->viewport()->width();
    if (available <= 0) {
        return;
    }
    if (!compactMode && panelWidth() > available) {
        build(true);
    }
    else if (compactMode && normalWidth <= available) {
        build(false);
    }
}

void RibbonBar::rebuild(const QStringList& toolbarNames)
{
    currentNames = toolbarNames;
    rebuildPending = false;
    ensureTabBar();

    build(false);
    fitToWidth();
    hideWorkbenchToolBars();
    updateHeight();
    // Se enkrat po obhodu dogodkov, ko so vsi gradniki gotovo prikazani in izmerjeni.
    QTimer::singleShot(0, this, [this]() { updateHeight(); });
}

void RibbonBar::scheduleRebuild()
{
    if (rebuildPending) {
        return;
    }
    rebuildPending = true;
    QTimer::singleShot(0, this, [this]() {
        if (rebuildPending) {
            rebuild(currentNames);
        }
    });
}

void RibbonBar::setToolBarShown(const QString& name, bool shown)
{
    if (shown) {
        forcedShown.insert(name);
        forcedHidden.remove(name);
    }
    else {
        forcedHidden.insert(name);
        forcedShown.remove(name);
    }
    scheduleRebuild();
}

void RibbonBar::resetToolBarShown(const QString& name)
{
    forcedShown.remove(name);
    forcedHidden.remove(name);
    scheduleRebuild();
}

void RibbonBar::hideWorkbenchToolBars()
{
    const QList<Gui::ToolBar*> toolbars = getMainWindow()->findChildren<Gui::ToolBar*>();
    for (Gui::ToolBar* toolbar : toolbars) {
        if (isGlobalToolBar(toolbar->objectName())) {
            continue;
        }
        if (toolbar->isVisible()) {
            toolbar->hide();
        }
        toolbar->toggleViewAction()->setVisible(false);
    }
}

void RibbonBar::updateHeight()
{
    panelLayout->activate();
    const QSize hint = panel->sizeHint();
    int height = hint.height();
    if (hint.width() > scroll->viewport()->width()) {
        height += scroll->horizontalScrollBar()->sizeHint().height();
    }
    scroll->setFixedHeight(height);
}

void RibbonBar::resizeEvent(QResizeEvent* event)
{
    QWidget::resizeEvent(event);
    if (event->oldSize().width() != event->size().width()) {
        fitToWidth();
    }
    updateHeight();
}

#include "moc_RibbonBar.cpp"
