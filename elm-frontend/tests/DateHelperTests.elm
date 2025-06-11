module DateHelperTests exposing (suite)

import Test exposing (Test, describe, test)
import Expect
import DateHelper exposing (diffDatesInDays, formatAsRssStyle, cutOffTralingZeroes)


suite : Test
suite =
    describe "DateHelper"
        [ describe "diffDatesInDays"
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