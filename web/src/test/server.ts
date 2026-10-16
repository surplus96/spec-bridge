// MSW: the API answers inside the test process; no server, no network. Display labels are
// a fixed default (a few names, so tests see both a label and the fallback).
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

export const labels = {
  origin: "synthetic",
  verified_by: null,
  classes: { FourStrokeEngine: "4행정 엔진" },
  attributes: { rated_power: "정격 출력", rated_throughput: "정격 처리량", maker: "제조사" },
  basis: {},
  condition: { rating_point: "정격점" },
};

export const server = setupServer(http.get("*/api/display", () => HttpResponse.json(labels)));
