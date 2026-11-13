module DateHelperTests exposing (suite)

import Test exposing (Test, describe, test)
import Expect
import DateHelper exposing (diffDatesInDays, formatAsRssStyle, cutOffTralingZeroes, parseRfcPosix, sellOutDuration)
import Time


suite : Test
suite =
    describe "DateHelper"
        [ describe "parseRfcPosix"
            [ test "parses UTC time" <|
                \_ ->
                    Expect.equal (Just 1794333900000)
                        (parseRfcPosix "Mon, 10 Nov 2026 18:05:00 +0000" |> Maybe.map Time.posixToMillis)
            , test "applies a negative offset" <|
                \_ ->
                    Expect.equal
                        (parseRfcPosix "Mon, 10 Nov 2026 18:00:00 +0000")
                        (parseRfcPosix "Mon, 10 Nov 2026 10:00:00 -0800")
            , test "applies a positive offset" <|
                \_ ->
                    Expect.equal
                        (parseRfcPosix "Mon, 10 Nov 2026 18:00:00 +0000")
                        (parseRfcPosix "Mon, 10 Nov 2026 19:30:00 +0130")
            , test "rejects garbage" <|
                \_ -> Expect.equal Nothing (parseRfcPosix "not a date")
            ]
        , describe "sellOutDuration"
            [ test "0 seconds" <| \_ -> Expect.equal (Just "1 min") (dur "2026-11-10T18:00:00Z")
            , test "59 seconds" <| \_ -> Expect.equal (Just "1 min") (dur "2026-11-10T18:00:59Z")
            , test "7 minutes" <| \_ -> Expect.equal (Just "7 min") (dur "2026-11-10T18:07:00Z")
            , test "59m59s" <| \_ -> Expect.equal (Just "59 min") (dur "2026-11-10T18:59:59Z")
            , test "60 minutes" <| \_ -> Expect.equal (Just "1 hour") (dur "2026-11-10T19:00:00Z")
            , test "3h30" <| \_ -> Expect.equal (Just "3 hours") (dur "2026-11-10T21:30:00Z")
            , test "23h59" <| \_ -> Expect.equal (Just "23 hours") (dur "2026-11-11T17:59:00Z")
            , test "24 hours" <| \_ -> Expect.equal (Just "1 day") (dur "2026-11-11T18:00:00Z")
            , test "50 hours" <| \_ -> Expect.equal (Just "2 days") (dur "2026-11-12T20:00:00Z")
            , test "sold_at before published" <| \_ -> Expect.equal (Just "1 min") (dur "2026-11-10T17:00:00Z")
            , test "unparseable sold_at" <| \_ -> Expect.equal Nothing (dur "nope")
            , test "unparseable published" <|
                \_ -> Expect.equal Nothing (sellOutDuration "nope" "2026-11-10T18:00:00Z")
            , test "applies non-UTC offset" <|
                \_ ->
                    Expect.equal (Just "1 min")
                        (sellOutDuration "Mon, 10 Nov 2026 10:00:00 -0800" "2026-11-10T18:00:00Z")
            ]
        , describe "diffDatesInDays"
            [ test "calculates difference between ISO and RFC dates" <|
                \_ ->
                    let
                        isoDate = "2024-03-15"
                        rfcDate = "Fri, 15 Mar 2024 13:46:00 +0000"
                    in
                    Expect.equal "0 days" (diffDatesInDays isoDate rfcDate)
            , test "handles different dates" <|
                \_ ->
                    let
                        isoDate = "2024-03-15"
                        rfcDate = "Sat, 16 Mar 2024 13:46:00 +0000"
                    in
                    Expect.equal "1 days" (diffDatesInDays isoDate rfcDate)
            , test "returns positive difference regardless of date order" <|
                \_ ->
                    let
                        isoDate = "2024-03-16"
                        rfcDate = "Fri, 15 Mar 2024 13:46:00 +0000"
                    in
                    Expect.equal "1 days" (diffDatesInDays isoDate rfcDate)
            , test "handles invalid ISO date" <|
                \_ ->
                    let
                        isoDate = "invalid-date"
                        rfcDate = "Fri, 15 Mar 2024 13:46:00 +0000"
                    in
                    Expect.equal "Could not parse one or both dates" (diffDatesInDays isoDate rfcDate)
            , test "handles invalid RFC date" <|
                \_ ->
                    let
                        isoDate = "2024-03-15"
                        rfcDate = "invalid-date"
                    in
                    Expect.equal "Could not parse one or both dates" (diffDatesInDays isoDate rfcDate)
            ]
        , test "formatAsRssStyle formats ISO date correctly" <|
            \_ ->
                let
                    input = "2025-06-08T15:01:51.437673"
                    expected = "Sun, 8 Jun 2025 15:01:51 +0000"
                in
                formatAsRssStyle input
                    |> Expect.equal expected
        , describe "cutOffTralingZeroes"
            [ test "removes trailing +0000 from date string" <|
                \_ ->
                    "2024-03-20 15:30:00 +0000"
                        |> cutOffTralingZeroes
                        |> Expect.equal "2024-03-20 15:30:00"
            , test "handles empty string" <|
                \_ ->
                    ""
                        |> cutOffTralingZeroes
                        |> Expect.equal ""
            , test "handles string without +0000" <|
                \_ ->
                    "2024-03-20 15:30:00"
                        |> cutOffTralingZeroes
                        |> Expect.equal "2024-03-20 15:30:00"
            ]
        ]


dur : String -> Maybe String
dur soldAt =
    sellOutDuration "Tue, 10 Nov 2026 18:00:00 +0000" soldAt
