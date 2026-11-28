#include "selfdrive/ui/qt/spinner.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <string>

#include <QApplication>
#include <QGridLayout>
#include <QPainter>
#include <QString>
#include <QTransform>

#include "system/hardware/hw.h"
#include "selfdrive/ui/qt/qt_window.h"
#include "selfdrive/ui/qt/util.h"

TrackWidget::TrackWidget(QWidget *parent) : QWidget(parent) {
  setAttribute(Qt::WA_OpaquePaintEvent);
  setFixedSize(spinner_size);

  // Smart Eco fork: the frog sits still while a soft blue (#1F6BFF) glow behind it pulses,
  // and his throat (vocal) sac puffs out twice per loop, like he's calling.
  QPixmap comma_img = loadPixmap("../assets/img_spinner_comma.png", spinner_size);
  QPixmap glow_img = loadPixmap("../assets/img_spinner_glow.png", spinner_size);
  const double f = spinner_size.width() / 848.0;  // the frog art is drawn on an 848 px canvas
  QPixmap sac_img = loadPixmap("../assets/img_spinner_sac.png", QSize(int(170 * f), int(140 * f)));
  const QPointF sac_center(640 * f, 372 * f);      // tucked under the jaw; drawn behind the frog so it grows out from under it

  auto bump = [](double x, double a, double b) {
    if (x < a || x > b) return 0.0;
    return std::pow(std::sin(M_PI * (x - a) / (b - a)), 1.5);
  };

  QPixmap pm(spinner_size);
  QPainter p(&pm);
  p.setRenderHint(QPainter::SmoothPixmapTransform);
  for (int i = 0; i < track_imgs.size(); ++i) {
    const double phase = double(i) / track_imgs.size();
    const double k = 0.2 + 0.8 * (0.5 - 0.5 * std::cos(2.0 * M_PI * phase));
    p.setOpacity(1.0);
    p.fillRect(0, 0, spinner_size.width(), spinner_size.height(), Qt::black);
    p.setOpacity(k);
    p.drawPixmap(0, 0, glow_img);
    p.setOpacity(1.0);

    const double puff = std::max(bump(phase, 0.05, 0.38), bump(phase, 0.52, 0.85));
    if (puff > 0.02 && !sac_img.isNull()) {
      const double sc = 0.3 + 0.7 * puff;
      const double w = sac_img.width() * sc, h = sac_img.height() * sc;
      const QPointF c(sac_center.x() - 30 * f * (1 - sc), sac_center.y() - 40 * f * (1 - sc));
      p.drawPixmap(QRectF(c.x() - w / 2, c.y() - h / 2, w, h), sac_img, QRectF(sac_img.rect()));
    }

    p.drawPixmap(0, 0, comma_img);
    track_imgs[i] = pm.copy();
  }

  m_anim.setDuration(2000);  // one slow breath every 2 s
  m_anim.setStartValue(0);
  m_anim.setEndValue(int(track_imgs.size() -1));
  m_anim.setLoopCount(-1);
  m_anim.start();
  connect(&m_anim, SIGNAL(valueChanged(QVariant)), SLOT(update()));
}

void TrackWidget::paintEvent(QPaintEvent *event) {
  QPainter painter(this);
  painter.drawPixmap(0, 0, track_imgs[m_anim.currentValue().toInt()]);
}

// Spinner

Spinner::Spinner(QWidget *parent) : QWidget(parent) {
  QGridLayout *main_layout = new QGridLayout(this);
  main_layout->setSpacing(0);
  main_layout->setMargin(200);

  main_layout->addWidget(new TrackWidget(this), 0, 0, Qt::AlignHCenter | Qt::AlignVCenter);

  text = new QLabel();
  text->setWordWrap(true);
  text->setVisible(false);
  text->setAlignment(Qt::AlignCenter);
  main_layout->addWidget(text, 1, 0, Qt::AlignHCenter);

  progress_bar = new QProgressBar();
  progress_bar->setRange(5, 100);
  progress_bar->setTextVisible(false);
  progress_bar->setVisible(false);
  progress_bar->setFixedHeight(20);
  main_layout->addWidget(progress_bar, 1, 0, Qt::AlignHCenter);

  setStyleSheet(R"(
    Spinner {
      background-color: black;
    }
    QLabel {
      color: white;
      font-size: 80px;
      background-color: transparent;
    }
    QProgressBar {
      background-color: #373737;
      width: 1000px;
      border solid white;
      border-radius: 10px;
    }
    QProgressBar::chunk {
      border-radius: 10px;
      background-color: rgba(23, 134, 68, 255);
    }
  )");

  notifier = new QSocketNotifier(fileno(stdin), QSocketNotifier::Read);
  QObject::connect(notifier, &QSocketNotifier::activated, this, &Spinner::update);
}

void Spinner::update(int n) {
  std::string line;
  std::getline(std::cin, line);

  if (line.length()) {
    bool number = std::all_of(line.begin(), line.end(), ::isdigit);
    text->setVisible(!number);
    progress_bar->setVisible(number);
    text->setText(QString::fromStdString(line));
    if (number) {
      progress_bar->setValue(std::stoi(line));
    }
  }
}

int main(int argc, char *argv[]) {
  initApp(argc, argv);
  QApplication a(argc, argv);
  Spinner spinner;
  setMainWindow(&spinner);
  return a.exec();
}
