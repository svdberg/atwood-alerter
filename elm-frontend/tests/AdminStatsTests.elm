module AdminStatsTests exposing (suite)

import AdminStats exposing (barHeights, failureRate, formatLastSent, monthLabel, statsDecoder)
import Expect
import Json.Decode as Decode
import Test exposing (Test, describe, test)


fixture : String
fixture =
    """
{
  "users": 38,
  "web_push": 14,
  "subscribers": {
    "email_confirmed": 30,
    "email_pending": 4,
    "web_push": 14
  },
  "notifications": {
    "posts_announced": 8,
    "email_recipients": 66,
    "push_success": 21,
    "push_failure": 2,
    "last_sent": "2026-11-10T18:07:00+00:00"
  },
  "monthly": [
    {
      "month": "2025-12",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-01",
      "posts_announced": 1,
      "email_recipients": 8,
      "push_success": 2,
      "push_failure": 0
    },
    {
      "month": "2026-02",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-03",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-04",
      "posts_announced": 2,
      "email_recipients": 12,
      "push_success": 3,
      "push_failure": 1
    },
    {
      "month": "2026-05",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-06",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-07",
      "posts_announced": 1,
      "email_recipients": 6,
      "push_success": 2,
      "push_failure": 0
    },
    {
      "month": "2026-08",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-09",
      "posts_announced": 1,
      "email_recipients": 10,
      "push_success": 4,
      "push_failure": 0
    },
    {
      "month": "2026-10",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": 0,
      "push_failure": 0
    },
    {
      "month": "2026-11",
      "posts_announced": 3,
      "email_recipients": 30,
      "push_success": 10,
      "push_failure": 1
    }
  ]
}
    """


nullFixture : String
nullFixture =
    """
{
  "users": 38,
  "web_push": 14,
  "subscribers": {
    "email_confirmed": null,
    "email_pending": 4,
    "web_push": 14
  },
  "notifications": {
    "posts_announced": 8,
    "email_recipients": 66,
    "push_success": null,
    "push_failure": null,
    "last_sent": "2026-11-10T18:07:00+00:00"
  },
  "monthly": [
    {
      "month": "2025-12",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-01",
      "posts_announced": 1,
      "email_recipients": 8,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-02",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-03",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-04",
      "posts_announced": 2,
      "email_recipients": 12,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-05",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-06",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-07",
      "posts_announced": 1,
      "email_recipients": 6,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-08",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-09",
      "posts_announced": 1,
      "email_recipients": 10,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-10",
      "posts_announced": 0,
      "email_recipients": 0,
      "push_success": null,
      "push_failure": null
    },
    {
      "month": "2026-11",
      "posts_announced": 3,
      "email_recipients": 30,
      "push_success": null,
      "push_failure": null
    }
  ]
}
    """


suite : Test
suite =
    describe "AdminStats"
        [ test "decodes the screenshot fixture" <|
            \_ ->
                case Decode.decodeString statsDecoder fixture of
                    Ok stats ->
                        Expect.all
                            [ \s -> Expect.equal 12 (List.length s.monthly)
                            , \s -> Expect.equal (Just 30) s.subscribers.emailConfirmed
                            , \s -> Expect.equal (Just 2) s.notifications.pushFailure
                            , \s -> Expect.equal (Just "2026-11-10T18:07:00+00:00") s.notifications.lastSent
                            ]
                            stats

                    Err e ->
                        Expect.fail (Decode.errorToString e)
        , test "decodes null fields as Nothing" <|
            \_ ->
                case Decode.decodeString statsDecoder nullFixture of
                    Ok stats ->
                        Expect.all
                            [ \s -> Expect.equal Nothing s.subscribers.emailConfirmed
                            , \s -> Expect.equal Nothing s.notifications.pushSuccess
                            , \s -> Expect.equal Nothing s.notifications.pushFailure
                            , \s -> Expect.equal True (List.all (\m -> m.pushSuccess == Nothing) s.monthly)
                            ]
                            stats

                    Err e ->
                        Expect.fail (Decode.errorToString e)
        , test "barHeights scales to the max" <|
            \_ -> Expect.equal [ 0, 50, 100 ] (barHeights 100 [ 0, 5, 10 ])
        , test "barHeights all zero stays zero" <|
            \_ -> Expect.equal [ 0, 0 ] (barHeights 100 [ 0, 0 ])
        , test "failureRate with no sends is Nothing" <|
            \_ -> Expect.equal Nothing (failureRate 0 0)
        , test "failureRate 9 1" <|
            \_ -> Expect.equal (Just 0.1) (failureRate 9 1)
        , test "formatLastSent" <|
            \_ -> Expect.equal "10 Nov 2026, 18:07 UTC" (formatLastSent "2026-11-10T18:07:00+00:00")
        , test "monthLabel" <|
            \_ ->
                Expect.equal [ "Jan 26", "Dec" ] [ monthLabel True "2026-01", monthLabel False "2025-12" ]
        ]
