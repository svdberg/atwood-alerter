module RecentReleasesTests exposing (suite)

import Expect
import Json.Decode as Decode
import RecentReleases exposing (Release, decoder, listDecoder, statusLabel)
import Test exposing (Test, describe, test)


release : Bool -> Maybe String -> Release
release sold soldAt =
    { title = "T"
    , url = "https://example.com"
    , published = "Tue, 10 Nov 2026 18:00:00 +0000"
    , imageUrl = ""
    , sold = sold
    , soldAt = soldAt
    }


suite : Test
suite =
    describe "RecentReleases"
        [ describe "statusLabel"
            [ test "available" <|
                \_ -> Expect.equal "Available" (statusLabel (release False Nothing))
            , test "sold with duration" <|
                \_ ->
                    Expect.equal "Sold out in 3 hours"
                        (statusLabel (release True (Just "2026-11-10T21:00:00Z")))
            , test "sold without sold_at" <|
                \_ -> Expect.equal "Sold out" (statusLabel (release True Nothing))
            , test "sold with unparseable sold_at" <|
                \_ -> Expect.equal "Sold out" (statusLabel (release True (Just "garbage")))
            ]
        , describe "decoder"
            [ test "accepts null image_url and null sold_at" <|
                \_ ->
                    Decode.decodeString decoder
                        """{"title":"T","url":"u","published":"p","image_url":null,"sold":true,"sold_at":null}"""
                        |> Expect.equal
                            (Ok { title = "T", url = "u", published = "p", imageUrl = "", sold = True, soldAt = Nothing })
            , test "accepts missing sold_at" <|
                \_ ->
                    Decode.decodeString decoder
                        """{"title":"T","url":"u","published":"p","image_url":"i","sold":false}"""
                        |> Expect.equal
                            (Ok { title = "T", url = "u", published = "p", imageUrl = "i", sold = False, soldAt = Nothing })
            , test "reads sold_at" <|
                \_ ->
                    Decode.decodeString decoder
                        """{"title":"T","url":"u","published":"p","image_url":"i","sold":true,"sold_at":"2026-11-10T18:07:00Z"}"""
                        |> Result.map .soldAt
                        |> Expect.equal (Ok (Just "2026-11-10T18:07:00Z"))
            ]
        , describe "listDecoder"
            [ test "missing recent_releases gives []" <|
                \_ ->
                    Decode.decodeString listDecoder """{"last_run_time":"x"}"""
                        |> Expect.equal (Ok [])
            , test "decodes a list" <|
                \_ ->
                    Decode.decodeString listDecoder
                        """{"recent_releases":[{"title":"T","url":"u","published":"p","image_url":null,"sold":false,"sold_at":null}]}"""
                        |> Result.map List.length
                        |> Expect.equal (Ok 1)
            ]
        ]
