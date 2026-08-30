import { expect, test } from "bun:test";
import { verifyBibliographicRecord } from "./bibliographic-verify.js";

test("bibliographic verification keeps resolution states distinct", async () => {
  const doiFetch = async () =>
    new Response(
      JSON.stringify({ message: { DOI: "10.1000/TEST", title: ["A Paper"] } }),
      { status: 200 },
    );
  const titleFetch = async () =>
    new Response(
      JSON.stringify({
        message: { items: [{ DOI: "10.1000/title", title: ["A: Paper!"] }] },
      }),
      { status: 200 },
    );

  expect(
    await verifyBibliographicRecord(
      { id: "doi", type: "article", DOI: "https://doi.org/10.1000/test" },
      "doi",
      doiFetch,
    ),
  ).toMatchObject({ status: "verified", method: "doi" });
  expect(
    await verifyBibliographicRecord(
      { id: "title", type: "article", title: "A Paper" },
      "title",
      titleFetch,
    ),
  ).toMatchObject({ status: "verified", method: "title" });
  expect(
    await verifyBibliographicRecord(undefined, "missing", doiFetch),
  ).toMatchObject({
    status: "unresolvable",
  });
  expect(
    await verifyBibliographicRecord(
      { id: "absent", type: "article", DOI: "10.1000/absent" },
      "absent",
      async () => new Response(null, { status: 404 }),
    ),
  ).toMatchObject({ status: "not_found" });
  expect(
    await verifyBibliographicRecord(
      { id: "offline", type: "article", DOI: "10.1000/offline" },
      "offline",
      async () => {
        throw new Error("offline");
      },
    ),
  ).toMatchObject({ status: "unavailable" });
});
