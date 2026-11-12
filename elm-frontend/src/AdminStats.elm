module AdminStats exposing
    ( Month
    , Notifications
    , Stats
    , Subscribers
    , barHeights
    , failureRate
    , formatLastSent
    , monthLabel
    , statsDecoder
    )

{-| Pure data types, decoder and chart helpers for the admin page.
-}

import Iso8601
import Json.Decode as Decode exposing (Decoder)
import Time


type alias Subscribers =
    { emailConfirmed : Maybe Int
    , emailPending : Maybe Int
    , webPush : Int
    }


type alias Notifications =
    { postsAnnounced : Int
    , emailRecipients : Int
    , pushSuccess : Maybe Int
    , pushFailure : Maybe Int
    , lastSent : Maybe String
    }


type alias Month =
    { month : String
    , postsAnnounced : Int
    , emailRecipients : Int
    , pushSuccess : Maybe Int
    , pushFailure : Maybe Int
    }


type alias Stats =
    { users : Int
    , webPush : Int
    , subscribers : Subscribers
    , notifications : Notifications
    , monthly : List Month
    }


statsDecoder : Decoder Stats
statsDecoder =
    Decode.map5 Stats
        (Decode.field "users" Decode.int)
        (Decode.field "web_push" Decode.int)
        (Decode.field "subscribers" subscribersDecoder)
        (Decode.field "notifications" notificationsDecoder)
        (Decode.field "monthly" (Decode.list monthDecoder))


subscribersDecoder : Decoder Subscribers
subscribersDecoder =
    Decode.map3 Subscribers
        (Decode.field "email_confirmed" (Decode.nullable Decode.int))
        (Decode.field "email_pending" (Decode.nullable Decode.int))
        (Decode.field "web_push" Decode.int)


notificationsDecoder : Decoder Notifications
notificationsDecoder =
    Decode.map5 Notifications
        (Decode.field "posts_announced" Decode.int)
        (Decode.field "email_recipients" Decode.int)
        (Decode.field "push_success" (Decode.nullable Decode.int))
        (Decode.field "push_failure" (Decode.nullable Decode.int))
        (Decode.field "last_sent" (Decode.nullable Decode.string))


monthDecoder : Decoder Month
monthDecoder =
    Decode.map5 Month
        (Decode.field "month" Decode.string)
        (Decode.field "posts_announced" Decode.int)
        (Decode.field "email_recipients" Decode.int)
        (Decode.field "push_success" (Decode.nullable Decode.int))
        (Decode.field "push_failure" (Decode.nullable Decode.int))


{-| Scale values so the largest becomes `maxHeight`. All zeros stay zero.
-}
barHeights : Float -> List Int -> List Float
barHeights maxHeight values =
    let
        top =
            List.maximum values |> Maybe.withDefault 0
    in
    if top <= 0 then
        List.map (\_ -> 0) values

    else
        List.map (\v -> toFloat v / toFloat top * maxHeight) values


{-| Share of failed pushes, or Nothing when nothing was sent.
-}
failureRate : Int -> Int -> Maybe Float
failureRate success failure =
    if success + failure <= 0 then
        Nothing

    else
        Just (toFloat failure / toFloat (success + failure))


monthNames : List String
monthNames =
    [ "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" ]


monthName : Int -> String
monthName n =
    monthNames |> List.drop (n - 1) |> List.head |> Maybe.withDefault "?"


{-| "2026-01" -> "Jan 26" when `withYear`, else "Jan".
-}
monthLabel : Bool -> String -> String
monthLabel withYear key =
    case String.split "-" key of
        [ year, m ] ->
            let
                name =
                    String.toInt m |> Maybe.map monthName |> Maybe.withDefault m
            in
            if withYear then
                name ++ " " ++ String.right 2 year

            else
                name

        _ ->
            key


{-| "2026-11-10T18:07:00+00:00" -> "10 Nov 2026, 18:07 UTC".
-}
formatLastSent : String -> String
formatLastSent iso =
    case Iso8601.toTime iso of
        Ok posix ->
            let
                pad n =
                    String.padLeft 2 '0' (String.fromInt n)

                monthNumber =
                    case Time.toMonth Time.utc posix of
                        Time.Jan ->
                            1

                        Time.Feb ->
                            2

                        Time.Mar ->
                            3

                        Time.Apr ->
                            4

                        Time.May ->
                            5

                        Time.Jun ->
                            6

                        Time.Jul ->
                            7

                        Time.Aug ->
                            8

                        Time.Sep ->
                            9

                        Time.Oct ->
                            10

                        Time.Nov ->
                            11

                        Time.Dec ->
                            12
            in
            String.fromInt (Time.toDay Time.utc posix)
                ++ " "
                ++ monthName monthNumber
                ++ " "
                ++ String.fromInt (Time.toYear Time.utc posix)
                ++ ", "
                ++ pad (Time.toHour Time.utc posix)
                ++ ":"
                ++ pad (Time.toMinute Time.utc posix)
                ++ " UTC"

        Err _ ->
            iso
