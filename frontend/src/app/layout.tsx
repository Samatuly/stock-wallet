import type { Metadata, Viewport } from "next";
import AppBar from "@/components/AppBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Wallet",
  description: "Личный кошелёк акций: позиции, цены, прибыль и убыток",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0b6e6b",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        {/* Space Grotesk — интерфейс и заголовки, IBM Plex Mono — все числа и тикеры,
            чтобы колонки цифр выравнивались как в биржевой ленте. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <AppBar />
        {children}
      </body>
    </html>
  );
}
