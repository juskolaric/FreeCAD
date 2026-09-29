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

#ifndef GUI_RIBBONBAR_H
#define GUI_RIBBONBAR_H

#include <QSet>
#include <QStringList>
#include <QToolButton>
#include <QWidget>

#include <FCGlobal.h>

class QAction;
class QActionEvent;
class QHBoxLayout;
class QResizeEvent;
class QScrollArea;
class QToolBar;
class QVBoxLayout;

namespace Gui
{

/// Velikost gumba v ukazni vrstici.
enum class RibbonButtonStyle
{
    Large,  ///< velika ikona, napis v dveh vrsticah spodaj
    Small,  ///< majhna ikona, napis ob strani
    Icon,   ///< samo ikona (zgosceni nacin, kot orodja skice v SolidWorksu)
};

/** Gumb ukazne vrstice. Napis sledi dejanju (prevod, sprememba besedila). */
class GuiExport RibbonButton: public QToolButton
{
    Q_OBJECT
public:
    RibbonButton(QAction* action, RibbonButtonStyle style, int iconSize, QWidget* parent = nullptr);

protected:
    void actionEvent(QActionEvent* event) override;

private:
    void applyText();

    RibbonButtonStyle style;
};

/** Ukazna vrstica v slogu SolidWorksovega CommandManagerja.
 *
 *  Zgoraj je vrstica zavihkov delovnih miz (isti gradnik kot izbirnik delovnih miz v obliki
 *  zavihkov), pod njo skupine gumbov, sestavljene iz orodnih vrstic aktivne delovne mize:
 *  skupina je del orodne vrstice med locili, prvih nekaj ukazov je velikih (ikona in napis
 *  spodaj), ostali so majhni v stolpcih po tri. Ce so skupine sirse od okna, se vrstica sama
 *  preklopi v zgosceni nacin (en velik gumb na skupino, ostali samo ikone), kot to naredi
 *  SolidWorks pri orodjih skice. Splosne orodne vrstice (Datoteka, Uredi, Pogled, Struktura,
 *  Pomoc ...) ostanejo klasicne, orodne vrstice delovnih miz so skrite.
 *
 *  Parametri v "User parameter:BaseApp/Preferences/RibbonBar":
 *    Enabled (bool, privzeto true; velja ob naslednjem zagonu),
 *    LargeIconSize (32), SmallIconSize (16), CompactIconSize (24), DefaultLargeCount (2),
 *    skupina LargeCount: <ime orodne vrstice> = stevilo velikih gumbov na skupino.
 */
class GuiExport RibbonBar: public QWidget
{
    Q_OBJECT
public:
    /// Ali je ukazna vrstica vklopljena (bere se enkrat ob zagonu).
    static bool isEnabled();
    /// Orodne vrstice, ki ostanejo klasicne (niso del ukazne vrstice).
    static bool isGlobalToolBar(const QString& name);
    static RibbonBar* instance();
    /// Ustvari edini primerek (klice glavno okno).
    static RibbonBar* create(QWidget* parent);

    /// Znova sestavi skupine iz orodnih vrstic z danimi imeni (vrstni red delovne mize).
    void rebuild(const QStringList& toolbarNames);
    /// Sestavi znova ob naslednjem obhodu dogodkov (vec zaporednih klicev se zdruzi).
    void scheduleRebuild();
    /// Prisilno prikaze ali skrije orodno vrstico (npr. urejanje skice) ne glede na privzeto vidnost.
    void setToolBarShown(const QString& name, bool shown);
    /// Odstrani prisilno stanje (nazaj na privzeto vidnost).
    void resetToolBarShown(const QString& name);
    /// Skrije klasicne orodne vrstice delovnih miz (jih nadomesca ukazna vrstica).
    void hideWorkbenchToolBars();

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    explicit RibbonBar(QWidget* parent);
    void ensureTabBar();
    void build(bool compact);
    void fitToWidth();
    QWidget* buildGroup(const QList<QAction*>& actions, QToolBar* source, int largeCount, bool compact);
    int largeCountFor(const QString& toolbarName) const;
    bool isToolBarShown(QToolBar* toolbar) const;
    int panelWidth();
    void updateHeight();

    static RibbonBar* _instance;

    QVBoxLayout* vbox = nullptr;
    QWidget* tabRow = nullptr;
    QHBoxLayout* tabLayout = nullptr;
    QWidget* tabWidget = nullptr;
    QScrollArea* scroll = nullptr;
    QWidget* panel = nullptr;
    QHBoxLayout* panelLayout = nullptr;

    QStringList currentNames;
    QSet<QString> forcedShown;
    QSet<QString> forcedHidden;
    int largeIcon = 32;
    int smallIcon = 16;
    int compactIcon = 24;
    int defaultLargeCount = 2;
    bool rebuildPending = false;
    bool compactMode = false;
    int normalWidth = 0;
};

}  // namespace Gui

#endif  // GUI_RIBBONBAR_H
