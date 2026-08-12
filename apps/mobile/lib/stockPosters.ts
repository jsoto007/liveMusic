/**
 * The house stock plates, one per genre — the same derivatives the web serves
 * from `public/stock/`, bundled here so a listing with no uploaded poster
 * still prints a photograph. Metro needs each asset named by a literal path,
 * so this map is written out by hand rather than derived from the shared
 * `STOCK_POSTERS` record; `lib/stockPosters.test.ts` holds the two in
 * lockstep and asserts the bundled files match the web's byte for byte.
 */

import type { ImageRequireSource } from "react-native";
import type { Genre } from "@live-msc/shared";

import classical from "../assets/stock/classical.jpg";
import electronic from "../assets/stock/electronic.jpg";
import festival from "../assets/stock/festival.jpg";
import folkCountry from "../assets/stock/folk_country.jpg";
import gospelSoul from "../assets/stock/gospel_soul.jpg";
import hipHop from "../assets/stock/hip_hop.jpg";
import jazz from "../assets/stock/jazz.jpg";
import metal from "../assets/stock/metal.jpg";
import openMic from "../assets/stock/open_mic.jpg";
import other from "../assets/stock/other.jpg";
import rockPunk from "../assets/stock/rock_punk.jpg";

export const stockPosters: Readonly<Record<Genre, ImageRequireSource>> = {
  rock_punk: rockPunk,
  jazz,
  classical,
  electronic,
  folk_country: folkCountry,
  metal,
  hip_hop: hipHop,
  gospel_soul: gospelSoul,
  open_mic: openMic,
  festival,
  other,
};
