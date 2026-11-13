-- TIME FORMATTING


module DateHelper exposing (cutOffTralingZeroes, diffDatesInDays, formatAsRssStyle, parseRfcPosix, sellOutDuration)

import Date exposing (Date)
import Iso8601
import Regex
import Result exposing (Result(..))
import String
import Time exposing (Month(..), Weekday(..), Zone, toHour, toMinute, toSecond, utc)


parseIsoDate : String -> Maybe Date
parseIsoDate isoString =
    -- Truncate to first 10 characters: "YYYY-MM-DD"
    String.left 10 isoString
        |> Date.fromIsoString
        |> Result.toMaybe


parseRfcDate : String -> Maybe Date
parseRfcDate rfcString =
    -- Expecting: "Tue, 03 Jun 2025 13:46:00 +0000"
    let
        regex =
            Maybe.withDefault Regex.never <|
                Regex.fromString "(\\d{2}) (\\w{3}) (\\d{4})"

        matches =
            Regex.find regex rfcString
    in
    case matches of
        match :: _ ->
            let
                parts =
                    match.submatches

                maybeDate =
                    case parts of
                        (Just dayStr) :: (Just monStr) :: (Just yearStr) :: _ ->
                            Maybe.map3
                                (\day month year -> Date.fromCalendarDate year month day)
                                (String.toInt dayStr)
                                (monthStrToInt monStr)
                                (String.toInt yearStr)

                        _ ->
                            Nothing
            in
            maybeDate

        _ ->
            Nothing


monthStrToInt : String -> Maybe Month
monthStrToInt str =
    case str of
        "Jan" ->
            Just Jan

        "Feb" ->
            Just Feb

        "Mar" ->
            Just Mar

        "Apr" ->
            Just Apr

        "May" ->
            Just May

        "Jun" ->
            Just Jun

        "Jul" ->
            Just Jul

        "Aug" ->
            Just Aug

        "Sep" ->
            Just Sep

        "Oct" ->
            Just Oct

        "Nov" ->
            Just Nov

        "Dec" ->
            Just Dec

        _ ->
            Nothing


diffDatesInDays : String -> String -> String
diffDatesInDays isoStr rfcStr =
    let
        maybeDate1 =
            parseIsoDate isoStr

        maybeDate2 =
            parseRfcDate rfcStr
    in
    case ( maybeDate1, maybeDate2 ) of
        ( Just d1, Just d2 ) ->
            let
                diff =
                    abs (Date.diff Date.Days d2 d1)
            in
            String.fromInt diff ++ " days"

        _ ->
            "Could not parse one or both dates"


formatAsRssStyle : String -> String
formatAsRssStyle isoStr =
    case Iso8601.toTime isoStr of
        Ok posix ->
            let
                zone : Zone
                zone =
                    utc

                date : Date
                date =
                    Date.fromPosix zone posix

                hour =
                    toHour zone posix

                minute =
                    toMinute zone posix

                second =
                    toSecond zone posix

                dayOfWeek =
                    case Date.weekday date of
                        Mon ->
                            "Mon"

                        Tue ->
                            "Tue"

                        Wed ->
                            "Wed"

                        Thu ->
                            "Thu"

                        Fri ->
                            "Fri"

                        Sat ->
                            "Sat"

                        Sun ->
                            "Sun"

                month =
                    case Date.month date of
                        Jan ->
                            "Jan"

                        Feb ->
                            "Feb"

                        Mar ->
                            "Mar"

                        Apr ->
                            "Apr"

                        May ->
                            "May"

                        Jun ->
                            "Jun"

                        Jul ->
                            "Jul"

                        Aug ->
                            "Aug"

                        Sep ->
                            "Sep"

                        Oct ->
                            "Oct"

                        Nov ->
                            "Nov"

                        Dec ->
                            "Dec"

                timeStr =
                    pad2 hour ++ ":" ++ pad2 minute ++ ":" ++ pad2 second
            in
            String.join " "
                [ dayOfWeek ++ ","
                , String.fromInt (Date.day date)
                , month
                , String.fromInt (Date.year date)
                , timeStr ++ " +0000"
                ]

        Err _ ->
            isoStr


cutOffTralingZeroes : String -> String
cutOffTralingZeroes s =
    let
        suffix =
            " +0000"
    in
    if String.endsWith suffix s then
        String.dropRight (String.length suffix) s

    else
        s


pad2 : Int -> String
pad2 n =
    if n < 10 then
        "0" ++ String.fromInt n

    else
        String.fromInt n


parseRfcPosix : String -> Maybe Time.Posix
parseRfcPosix rfcString =
    -- Expecting: "Mon, 10 Nov 2026 18:05:00 +0000"
    let
        regex =
            Maybe.withDefault Regex.never <|
                Regex.fromString "(\\d{1,2}) (\\w{3}) (\\d{4}) (\\d{2}):(\\d{2}):(\\d{2}) ([+-])(\\d{2})(\\d{2})"

        toPosix day month year timeSeconds sign offsetMinutes =
            let
                days =
                    Date.toRataDie (Date.fromCalendarDate year month day) - 719163

                signed =
                    if sign == "-" then
                        -offsetMinutes

                    else
                        offsetMinutes
            in
            Time.millisToPosix ((days * 86400 + timeSeconds - signed * 60) * 1000)

        ints =
            List.map (Maybe.andThen String.toInt)
    in
    case Regex.find regex rfcString of
        match :: _ ->
            case match.submatches of
                [ day, monStr, year, hh, mm, ss, Just sign, oh, om ] ->
                    case ints [ day, year, hh, mm, ss, oh, om ] of
                        [ Just d, Just y, Just h, Just m, Just s, Just offH, Just offM ] ->
                            Maybe.map
                                (\month -> toPosix d month y (h * 3600 + m * 60 + s) sign (offH * 60 + offM))
                                (monStr |> Maybe.andThen monthStrToInt)

                        _ ->
                            Nothing

                _ ->
                    Nothing

        [] ->
            Nothing


sellOutDuration : String -> String -> Maybe String
sellOutDuration published soldAt =
    Maybe.map2
        (\pub sold ->
            let
                d =
                    max 0 ((Time.posixToMillis sold - Time.posixToMillis pub) // 1000)
            in
            if d < 3600 then
                String.fromInt (max 1 (d // 60)) ++ " min"

            else if d < 86400 then
                plural (d // 3600) "hour"

            else
                plural (d // 86400) "day"
        )
        (parseRfcPosix published)
        (Iso8601.toTime soldAt |> Result.toMaybe)


plural : Int -> String -> String
plural n unit =
    String.fromInt n
        ++ " "
        ++ unit
        ++ (if n == 1 then
                ""

            else
                "s"
           )
